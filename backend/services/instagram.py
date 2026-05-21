"""
Instagram integration via Playwright browser automation.
Replaces the instagrapi-based implementation.

Public interface (unchanged for callers in celery_app.py and api/accounts.py):
  PENDING_CHALLENGES      dict
  encrypt_session()       helper
  decrypt_session()       helper
  save_session()
  begin_challenge_login()
  complete_challenge_login()
  login_by_sessionid()
  restore_session()
  poll_inbox()
  send_dm()
  fetch_user_info()
  send_outbound_dm()
"""

import json
import logging
import random
import time
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import unquote

from cryptography.fernet import InvalidToken
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from sqlalchemy.orm import Session

from config import cipher
from models.account import Account, BotStatus

logger = logging.getLogger(__name__)

PENDING_CHALLENGES: dict = {}
_CHALLENGE_TTL_SECONDS = 600


# ---------------------------------------------------------------------------
# Data models — duck-type compatible with what celery_app.py expects
# ---------------------------------------------------------------------------

@dataclass
class IGUser:
    username: str
    pk: int


@dataclass
class IGMessage:
    user_id: int
    timestamp: datetime
    text: Optional[str]


@dataclass
class IGThread:
    id: str
    users: list
    messages: list
    viewer_id: Optional[int]


class PlaywrightSession:
    """
    Duck-type wrapper so callers can do save_session(result["cl"], account, db)
    without knowing about Playwright internals.
    """
    def __init__(self, storage_state: dict):
        self._state = storage_state

    def get_settings(self) -> dict:
        return self._state


# ---------------------------------------------------------------------------
# Session encryption (same Fernet approach as before)
# ---------------------------------------------------------------------------

def encrypt_session(data: dict) -> str:
    return cipher.encrypt(json.dumps(data).encode()).decode()


def decrypt_session(encrypted: str) -> dict:
    return json.loads(cipher.decrypt(encrypted.encode()).decode())


def save_session(cl_or_state, account: Account, db: Session) -> None:
    """Save Playwright storage state to DB. Accepts PlaywrightSession or raw dict."""
    try:
        if isinstance(cl_or_state, dict):
            state = cl_or_state
        else:
            state = cl_or_state.get_settings()
        account.session_data = encrypt_session(state)
        db.commit()
        logger.debug("account=%s session saved", account.username)
    except Exception as exc:
        db.rollback()
        logger.error("account=%s failed to save session: %s", account.username, exc, exc_info=True)
        raise


def _get_storage_state(account: Account) -> Optional[dict]:
    if not account.session_data:
        return None
    try:
        return decrypt_session(account.session_data)
    except (InvalidToken, json.JSONDecodeError, Exception) as exc:
        logger.error("account=%s failed to decrypt session: %s", account.username, exc)
        return None


# ---------------------------------------------------------------------------
# Proxy parsing
# ---------------------------------------------------------------------------

def _parse_proxy(proxy_url: Optional[str]) -> Optional[dict]:
    """
    Accept two formats:
      JSON: '{"server":"http://host:port","username":"u","password":"p"}'
      URL:  'http://user:pass@host:port'
    Returns Playwright proxy dict or None.
    """
    if not proxy_url:
        return None
    s = proxy_url.strip()
    if s.startswith("{"):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
    return {"server": s}


# ---------------------------------------------------------------------------
# Browser helpers
# ---------------------------------------------------------------------------

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _launch_context(pw, proxy_dict: Optional[dict], storage_state: Optional[dict] = None):
    """Launch Chromium and return (browser, context). Caller must close both."""
    browser = pw.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-extensions",
        ],
    )
    kwargs = dict(
        user_agent=_USER_AGENT,
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="America/New_York",
    )
    if proxy_dict:
        kwargs["proxy"] = proxy_dict
    if storage_state:
        kwargs["storage_state"] = storage_state

    context = browser.new_context(**kwargs)
    context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    )
    return browser, context


def _human_delay(min_s: float = 1.5, max_s: float = 4.0) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _purge_expired_challenges() -> None:
    now = time.time()
    expired = [
        t for t, v in list(PENDING_CHALLENGES.items())
        if now - v.get("created_at", now) > _CHALLENGE_TTL_SECONDS
    ]
    for t in expired:
        PENDING_CHALLENGES.pop(t, None)
    if expired:
        logger.info("purged %d expired challenge token(s)", len(expired))


def _dismiss_popups(page) -> None:
    """Dismiss common post-login popups (save info, notifications, cookies)."""
    selectors = [
        'button:has-text("Not Now")',
        'button:has-text("Allow all cookies")',
        'button:has-text("Save Info")',
        '[aria-label="Close"]',
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1500):
                btn.click()
                _human_delay(0.3, 0.8)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Login flows
# ---------------------------------------------------------------------------

def begin_challenge_login(username: str, password: str, proxy_url: str = None) -> dict:
    """
    Log in via real Instagram web UI.
    Returns:
      {"type": "success", "cl": PlaywrightSession}
      {"type": "challenge", "token": str, "hint": str}
    Raises RuntimeError on hard failures (bad credentials, rate limit).
    """
    _purge_expired_challenges()
    proxy_dict = _parse_proxy(proxy_url)

    with sync_playwright() as pw:
        browser, context = _launch_context(pw, proxy_dict)
        page = context.new_page()
        try:
            logger.info("account=%s opening Instagram login page", username)
            page.goto(
                "https://www.instagram.com/accounts/login/",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            _human_delay(2.0, 3.5)
            _dismiss_popups(page)

            page.fill('input[name="username"]', username)
            _human_delay(0.4, 1.0)
            page.fill('input[name="password"]', password)
            _human_delay(0.5, 1.2)
            page.click('button[type="submit"]')

            # Wait for result: home, challenge, or 2FA
            try:
                page.wait_for_function(
                    """() => {
                        const url = window.location.href;
                        return (
                            url.includes('/challenge') ||
                            url.includes('/two_factor') ||
                            url.includes('/onetap') ||
                            (url === 'https://www.instagram.com/' || url.endsWith('.com/')) ||
                            document.querySelector('[data-testid="login-error-message"]') !== null ||
                            document.querySelector('p[role="alert"]') !== null
                        );
                    }""",
                    timeout=25_000,
                )
            except PlaywrightTimeout:
                raise RuntimeError(
                    "Instagram login timed out — IP may be rate-limited. Try a proxy."
                )

            current_url = page.url

            # Hard error: still on login page with error message
            if "/accounts/login/" in current_url:
                err_el = page.locator(
                    '[data-testid="login-error-message"], p[role="alert"]'
                ).first
                err_text = ""
                try:
                    err_text = err_el.text_content(timeout=2000) or ""
                except Exception:
                    pass
                raise RuntimeError(
                    f"Instagram login failed: {err_text or 'wrong credentials or IP blocked'}"
                )

            # Challenge / 2FA required
            if any(x in current_url for x in ("challenge", "two_factor")):
                hint = _extract_challenge_hint(page)
                token = str(_uuid.uuid4())
                storage = context.storage_state()
                PENDING_CHALLENGES[token] = {
                    "storage_state": storage,
                    "challenge_url": current_url,
                    "username": username,
                    "password": password,
                    "proxy_url": proxy_url,
                    "hint": hint,
                    "created_at": time.time(),
                }
                logger.info(
                    "account=%s challenge detected url=%s token=%s hint=%s",
                    username, current_url, token, hint,
                )
                return {"type": "challenge", "token": token, "hint": hint}

            # Success — dismiss any post-login popups
            _human_delay(1.0, 2.0)
            _dismiss_popups(page)
            storage = context.storage_state()
            logger.info("account=%s login successful", username)
            return {"type": "success", "cl": PlaywrightSession(storage)}

        finally:
            context.close()
            browser.close()


def _extract_challenge_hint(page) -> str:
    """Try to extract email/phone hint from Instagram challenge page."""
    try:
        # Look for masked email or phone in the challenge page text
        for sel in [
            'span:has-text("@")',
            'span:has-text("+")',
            "[class*='challenge'] span",
            "form span",
        ]:
            el = page.locator(sel).first
            text = el.text_content(timeout=1500)
            if text and (("@" in text and "." in text) or text.startswith("+")):
                return text.strip()
    except Exception:
        pass
    return ""


def complete_challenge_login(token: str, code: str, account: Account, db: Session) -> PlaywrightSession:
    """Submit the verification code and finish login. Saves session on success."""
    stored = PENDING_CHALLENGES.pop(token, None)
    if not stored:
        raise ValueError("Challenge expired or not found. Please try connecting again.")

    proxy_dict = _parse_proxy(stored.get("proxy_url"))
    challenge_url = stored.get("challenge_url", "https://www.instagram.com/challenge/")

    with sync_playwright() as pw:
        browser, context = _launch_context(pw, proxy_dict, storage_state=stored["storage_state"])
        page = context.new_page()
        try:
            # Return to the challenge page with the stored session
            page.goto(challenge_url, wait_until="domcontentloaded", timeout=20_000)
            _human_delay(1.0, 2.0)

            # Find and fill the code input
            code_input = page.locator(
                'input[name="security_code"], '
                'input[autocomplete="one-time-code"], '
                'input[inputmode="numeric"], '
                'input[type="text"]',
            ).first
            code_input.click()
            _human_delay(0.3, 0.7)
            code_input.fill(code.strip())
            _human_delay(0.5, 1.0)

            # Submit
            submit = page.locator(
                'button[type="submit"], button:has-text("Confirm"), button:has-text("Submit")'
            ).first
            submit.click()

            # Wait for redirect away from challenge
            try:
                page.wait_for_function(
                    "() => !window.location.href.includes('challenge') && "
                    "!window.location.href.includes('two_factor')",
                    timeout=15_000,
                )
            except PlaywrightTimeout:
                raise ValueError("Code verification timed out. Please try again.")

            _human_delay(1.0, 2.0)
            _dismiss_popups(page)

            storage = context.storage_state()
            session = PlaywrightSession(storage)
            save_session(session, account, db)
            logger.info("account=%s challenge completed, session saved", account.username)
            return session

        finally:
            context.close()
            browser.close()


def login_by_sessionid(
    session_id: str, account: Account, db: Session, proxy_url: str = None
) -> PlaywrightSession:
    """
    Inject a browser sessionid cookie and verify the session is alive.
    Saves storage state on success.
    """
    decoded = unquote(session_id.strip())
    parts = decoded.split(":")
    if not parts[0].isdigit():
        raise ValueError(f"Could not extract user_id from session ID: {decoded[:20]}...")
    user_id_str = parts[0]

    proxy_dict = _parse_proxy(proxy_url)

    with sync_playwright() as pw:
        browser, context = _launch_context(pw, proxy_dict)
        context.add_cookies([
            {
                "name": "sessionid",
                "value": decoded,
                "domain": ".instagram.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            },
            {
                "name": "ds_user_id",
                "value": user_id_str,
                "domain": ".instagram.com",
                "path": "/",
                "secure": True,
            },
        ])
        page = context.new_page()
        try:
            page.goto(
                "https://www.instagram.com/",
                wait_until="domcontentloaded",
                timeout=20_000,
            )
            _human_delay(2.0, 3.0)

            if "accounts/login" in page.url:
                raise ValueError("Session ID is invalid or expired (redirected to login page)")

            _dismiss_popups(page)
            storage = context.storage_state()
            session = PlaywrightSession(storage)
            save_session(session, account, db)
            logger.info("account=%s logged in via session ID", account.username)
            return session

        finally:
            context.close()
            browser.close()


def restore_session(account: Account, db: Session) -> bool:
    """Verify that the stored browser session is still valid."""
    storage = _get_storage_state(account)
    if not storage:
        return False

    proxy_dict = _parse_proxy(account.proxy_url)
    with sync_playwright() as pw:
        browser, context = _launch_context(pw, proxy_dict, storage_state=storage)
        page = context.new_page()
        try:
            page.goto(
                "https://www.instagram.com/",
                wait_until="domcontentloaded",
                timeout=15_000,
            )
            _human_delay(1.0, 2.0)
            alive = "accounts/login" not in page.url
            if alive:
                # Refresh session while we're here
                new_storage = context.storage_state()
                account.session_data = encrypt_session(new_storage)
                try:
                    db.commit()
                except Exception:
                    db.rollback()
            logger.info("account=%s session check: %s", account.username, "alive" if alive else "expired")
            return alive
        except Exception as exc:
            logger.warning("account=%s restore_session error: %s", account.username, exc)
            return False
        finally:
            context.close()
            browser.close()


# ---------------------------------------------------------------------------
# Inbox polling
# ---------------------------------------------------------------------------

def poll_inbox(account: Account, db: Session) -> list:
    """
    Fetch DM threads from instagram.com/direct/inbox/ by intercepting the
    Instagram internal API response. Returns list of IGThread objects.
    """
    from services.anti_ban import handle_instagram_error

    storage = _get_storage_state(account)
    if not storage:
        logger.error("account=%s no session — cannot poll", account.username)
        handle_instagram_error(account, db, "NoSession")
        return []

    proxy_dict = _parse_proxy(account.proxy_url)
    captured: list[dict] = []

    def _on_response(response):
        if "direct_v2/inbox" in response.url and response.status == 200:
            try:
                captured.append(response.json())
            except Exception:
                pass

    with sync_playwright() as pw:
        browser, context = _launch_context(pw, proxy_dict, storage_state=storage)
        page = context.new_page()
        page.on("response", _on_response)
        try:
            page.goto(
                "https://www.instagram.com/direct/inbox/",
                wait_until="networkidle",
                timeout=35_000,
            )
            _human_delay(2.0, 3.5)

            if "accounts/login" in page.url:
                logger.warning("account=%s session expired (redirected to login)", account.username)
                handle_instagram_error(account, db, "LoginRequired")
                return []

            # Fallback: make the API call from inside the browser if interception missed it
            if not captured:
                logger.debug("account=%s inbox interception missed, trying direct fetch", account.username)
                try:
                    result = page.evaluate(
                        """async () => {
                            const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
                            const r = await fetch(
                                '/api/v1/direct_v2/inbox/?thread_message_limit=10&limit=20',
                                {headers: {'X-CSRFToken': csrf, 'X-IG-App-ID': '936619743392459'}}
                            );
                            return r.ok ? await r.json() : null;
                        }"""
                    )
                    if result:
                        captured.append(result)
                except Exception as exc:
                    logger.warning("account=%s fallback inbox fetch failed: %s", account.username, exc)

            # Refresh session
            new_storage = context.storage_state()
            account.session_data = encrypt_session(new_storage)
            try:
                db.commit()
            except Exception:
                db.rollback()

        except PlaywrightTimeout:
            logger.warning("account=%s inbox page timeout", account.username)
            handle_instagram_error(account, db, "TimeoutError")
            return []
        except Exception as exc:
            logger.error("account=%s poll_inbox error: %s", account.username, exc, exc_info=True)
            handle_instagram_error(account, db, f"UnexpectedError:{type(exc).__name__}")
            return []
        finally:
            context.close()
            browser.close()

    if not captured:
        logger.warning("account=%s no inbox data captured", account.username)
        return []

    return _parse_inbox_response(captured[0], account.username)


def _parse_inbox_response(raw: dict, username: str) -> list:
    """Convert raw Instagram inbox API JSON into list of IGThread."""
    threads = []
    try:
        viewer_pk = (
            raw.get("viewer", {}).get("pk")
            or raw.get("viewer", {}).get("id")
        )
        raw_threads = raw.get("inbox", {}).get("threads", [])

        for rt in raw_threads:
            thread_id = str(rt.get("thread_id", ""))
            if not thread_id:
                continue

            viewer_id = _to_int(rt.get("viewer_id") or viewer_pk)

            users = [
                IGUser(
                    username=u.get("username", "unknown"),
                    pk=_to_int(u.get("pk") or u.get("id", 0)),
                )
                for u in rt.get("users", [])
            ]

            messages = []
            for item in rt.get("items", []):
                ts_raw = item.get("timestamp", 0)
                try:
                    ts = datetime.fromtimestamp(int(ts_raw) / 1_000_000, tz=timezone.utc)
                except Exception:
                    ts = datetime.now(timezone.utc)

                messages.append(IGMessage(
                    user_id=_to_int(item.get("user_id", 0)),
                    timestamp=ts,
                    text=item.get("text"),
                ))

            threads.append(IGThread(
                id=thread_id,
                users=users,
                messages=messages,
                viewer_id=viewer_id,
            ))

    except Exception as exc:
        logger.error("account=%s inbox parse error: %s", username, exc, exc_info=True)

    logger.debug("account=%s parsed %d threads", username, len(threads))
    return threads


def _to_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Send DM (reply to existing thread)
# ---------------------------------------------------------------------------

def send_dm(account: Account, thread_id: str, text: str, db: Session) -> bool:
    """Navigate to an existing DM thread and send a message via the web UI."""
    from services.anti_ban import handle_instagram_error, get_typing_duration

    storage = _get_storage_state(account)
    if not storage:
        handle_instagram_error(account, db, "NoSession")
        return False

    proxy_dict = _parse_proxy(account.proxy_url)

    # Simulate typing time before even opening the browser
    duration = get_typing_duration(len(text))
    logger.debug(
        "account=%s simulating typing %.1fs before sending to thread=%s",
        account.username, duration, thread_id,
    )
    time.sleep(duration)

    with sync_playwright() as pw:
        browser, context = _launch_context(pw, proxy_dict, storage_state=storage)
        page = context.new_page()
        try:
            url = f"https://www.instagram.com/direct/t/{thread_id}/"
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            _human_delay(2.0, 3.5)

            if "accounts/login" in page.url:
                logger.warning("account=%s session expired during send_dm", account.username)
                handle_instagram_error(account, db, "LoginRequired")
                return False

            # Instagram DM input is a contenteditable div
            msg_box = page.locator(
                'div[role="textbox"][contenteditable="true"], '
                'textarea[placeholder]'
            ).last
            msg_box.wait_for(state="visible", timeout=10_000)
            msg_box.click()
            _human_delay(0.4, 0.9)

            # Type with human-like keystroke delays
            msg_box.type(text, delay=random.randint(35, 90))
            _human_delay(0.5, 1.2)
            page.keyboard.press("Enter")
            _human_delay(1.0, 2.0)

            # Refresh session
            new_storage = context.storage_state()
            account.session_data = encrypt_session(new_storage)
            try:
                db.commit()
            except Exception:
                db.rollback()

            logger.info(
                "account=%s sent DM to thread=%s (%d chars)",
                account.username, thread_id, len(text),
            )
            return True

        except PlaywrightTimeout:
            logger.warning("account=%s send_dm timeout thread=%s", account.username, thread_id)
            handle_instagram_error(account, db, "TimeoutError")
            return False
        except Exception as exc:
            logger.error(
                "account=%s send_dm error thread=%s: %s",
                account.username, thread_id, exc, exc_info=True,
            )
            handle_instagram_error(account, db, f"UnexpectedError:{type(exc).__name__}")
            return False
        finally:
            context.close()
            browser.close()


# ---------------------------------------------------------------------------
# User info lookup
# ---------------------------------------------------------------------------

def fetch_user_info(username: str, account: Account, db: Session) -> dict:
    """Returns dict with full_name and user_id. Falls back to username on failure."""
    storage = _get_storage_state(account)
    if not storage:
        return {"user_id": None, "full_name": username}

    proxy_dict = _parse_proxy(account.proxy_url)
    profile_data: list[dict] = []

    def _on_response(response):
        if "web_profile_info" in response.url and response.status == 200:
            try:
                profile_data.append(response.json())
            except Exception:
                pass

    with sync_playwright() as pw:
        browser, context = _launch_context(pw, proxy_dict, storage_state=storage)
        page = context.new_page()
        page.on("response", _on_response)
        try:
            page.goto(
                f"https://www.instagram.com/{username}/",
                wait_until="networkidle",
                timeout=20_000,
            )
            _human_delay(1.0, 2.0)

            user_id = None
            full_name = username

            if profile_data:
                udata = profile_data[0].get("data", {}).get("user", {})
                user_id = str(udata.get("id", "")) or None
                full_name = udata.get("full_name") or username

            return {"user_id": user_id, "full_name": full_name}

        except Exception as exc:
            logger.warning("fetch_user_info failed for @%s: %s", username, exc)
            return {"user_id": None, "full_name": username}
        finally:
            context.close()
            browser.close()


# ---------------------------------------------------------------------------
# Outbound DM (start new conversation)
# ---------------------------------------------------------------------------

def send_outbound_dm(
    account: Account, instagram_username: str, text: str, db: Session
) -> Optional[str]:
    """
    Start a new DM conversation with instagram_username.
    Returns thread_id on success, None on failure.
    """
    from services.anti_ban import handle_instagram_error, get_typing_duration

    storage = _get_storage_state(account)
    if not storage:
        handle_instagram_error(account, db, "NoSession")
        return None

    proxy_dict = _parse_proxy(account.proxy_url)

    duration = get_typing_duration(len(text))
    time.sleep(duration)

    with sync_playwright() as pw:
        browser, context = _launch_context(pw, proxy_dict, storage_state=storage)
        page = context.new_page()
        try:
            page.goto(
                "https://www.instagram.com/direct/inbox/",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            _human_delay(2.0, 3.5)

            if "accounts/login" in page.url:
                handle_instagram_error(account, db, "LoginRequired")
                return None

            # Click compose / new message button
            compose = page.locator(
                'a[href="/direct/new/"], '
                'svg[aria-label="New message"], '
                'button[aria-label="New message"]'
            ).first
            compose.wait_for(state="visible", timeout=8_000)
            compose.click()
            _human_delay(1.0, 2.0)

            # Search for the target user
            search = page.locator(
                'input[name="queryBox"], '
                'input[placeholder*="Search"], '
                'input[aria-label*="Search"]'
            ).first
            search.wait_for(state="visible", timeout=6_000)
            search.type(instagram_username, delay=random.randint(60, 120))
            _human_delay(2.0, 3.0)

            # Click first matching result
            result = page.locator(
                f'div[role="button"]:has-text("{instagram_username}"), '
                f'button:has-text("{instagram_username}")'
            ).first
            result.wait_for(state="visible", timeout=6_000)
            result.click()
            _human_delay(0.8, 1.5)

            # Confirm selection (Chat / Next button)
            next_btn = page.locator(
                'button:has-text("Chat"), button:has-text("Next")'
            ).first
            next_btn.wait_for(state="visible", timeout=5_000)
            next_btn.click()
            _human_delay(2.0, 3.0)

            # Type and send message
            msg_box = page.locator(
                'div[role="textbox"][contenteditable="true"], textarea[placeholder]'
            ).last
            msg_box.wait_for(state="visible", timeout=8_000)
            msg_box.click()
            _human_delay(0.4, 0.9)
            msg_box.type(text, delay=random.randint(35, 90))
            _human_delay(0.5, 1.2)
            page.keyboard.press("Enter")
            _human_delay(1.5, 2.5)

            # Extract thread_id from URL
            current_url = page.url
            thread_id = None
            if "/direct/t/" in current_url:
                thread_id = current_url.split("/direct/t/")[-1].strip("/")

            # Refresh session
            new_storage = context.storage_state()
            account.session_data = encrypt_session(new_storage)
            try:
                db.commit()
            except Exception:
                db.rollback()

            if thread_id:
                logger.info(
                    "account=%s outbound DM sent to @%s thread=%s",
                    account.username, instagram_username, thread_id,
                )
                return thread_id

            logger.warning(
                "account=%s outbound DM sent but thread_id not found in URL=%s",
                account.username, current_url,
            )
            return None

        except Exception as exc:
            logger.error(
                "account=%s send_outbound_dm to @%s failed: %s",
                account.username, instagram_username, exc, exc_info=True,
            )
            handle_instagram_error(account, db, f"OutboundError:{type(exc).__name__}")
            return None
        finally:
            context.close()
            browser.close()
