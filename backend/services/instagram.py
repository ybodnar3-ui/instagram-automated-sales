import json
import logging
import time
import uuid as _uuid
from typing import Optional
from urllib.parse import unquote
from cryptography.fernet import InvalidToken
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, LoginRequired, PleaseWaitFewMinutes
from sqlalchemy.orm import Session
from config import cipher
from models.account import Account, BotStatus

PENDING_CHALLENGES: dict = {}  # token -> stored challenge state
_CHALLENGE_TTL_SECONDS = 600  # 10 minutes


def _purge_expired_challenges() -> None:
    now = time.time()
    expired = [t for t, v in PENDING_CHALLENGES.items() if now - v.get("created_at", now) > _CHALLENGE_TTL_SECONDS]
    for t in expired:
        PENDING_CHALLENGES.pop(t, None)
    if expired:
        logger.info("purged %d expired challenge token(s)", len(expired))


class _PauseForCode(Exception):
    """Raised by our challenge_code_handler to pause the flow after code is dispatched."""

logger = logging.getLogger(__name__)


def encrypt_session(session_dict: dict) -> str:
    return cipher.encrypt(json.dumps(session_dict).encode()).decode()


def decrypt_session(encrypted: str) -> dict:
    return json.loads(cipher.decrypt(encrypted.encode()).decode())


def get_instagram_client(account: Account) -> Client:
    cl = Client()
    if account.proxy_url:
        cl.set_proxy(account.proxy_url)
    if account.session_data:
        try:
            session = decrypt_session(account.session_data)
            cl.set_settings(session)
            if account.proxy_url:
                cl.set_proxy(account.proxy_url)  # re-apply after set_settings
        except (InvalidToken, json.JSONDecodeError, Exception) as exc:
            logger.error(
                "account=%s could not decrypt session, will require fresh login: %s",
                account.username, exc,
            )
    return cl


def save_session(cl: Client, account: Account, db: Session) -> None:
    account.session_data = encrypt_session(cl.get_settings())
    db.commit()


def login_and_save(username: str, password: str, account: Account, db: Session) -> Client:
    logger.info("account=%s initiating Instagram login", username)
    cl = Client()
    cl.login(username, password)
    save_session(cl, account, db)
    logger.info("account=%s login successful, session saved", username)
    return cl


def begin_challenge_login(username: str, password: str, proxy_url: str = None) -> dict:  # noqa: C901
    """
    Attempts login and handles Instagram challenge flows.

    Returns one of:
      {"type": "success", "cl": <Client>}           — logged in, no challenge
      {"type": "challenge", "token": str, "hint": str} — code sent, awaiting user input
    Raises on hard failures (bad credentials, unexpected errors).
    """
    _purge_expired_challenges()
    cl = Client()
    if proxy_url:
        cl.set_proxy(proxy_url)
    try:
        cl.login(username, password)
        logger.info("account=%s direct login success", username)
        return {"type": "success", "cl": cl}
    except ChallengeRequired:
        pass

    last_json = cl.last_json
    step_name = last_json.get("step_name", "")
    logger.info("account=%s challenge required, step=%s", username, step_name)

    # Auto-resolvable: "Was this you?" style
    if step_name in ("delta_login_review", "scraping_warning"):
        try:
            cl.challenge_resolve(last_json)
            logger.info("account=%s auto-resolved challenge step=%s", username, step_name)
        except Exception as exc:
            logger.warning("account=%s auto-resolve failed: %s", username, exc)
        time.sleep(2)
        cl2 = Client()
        if proxy_url:
            cl2.set_proxy(proxy_url)
        cl2.login(username, password)
        logger.info("account=%s retry login success after auto-challenge", username)
        return {"type": "success", "cl": cl2}

    # Code challenge: send code to user then pause
    step_data = last_json.get("step_data", {})
    hint = step_data.get("email") or step_data.get("phone_number") or ""

    def _pause(u, c):
        raise _PauseForCode()

    cl.challenge_code_handler = _pause

    try:
        cl.challenge_resolve(last_json)
        # Resolved without needing user code (shouldn't happen here, but handle it)
        return {"type": "success", "cl": cl}
    except _PauseForCode:
        token = str(_uuid.uuid4())
        PENDING_CHALLENGES[token] = {
            "settings": cl.get_settings(),
            "challenge_url": last_json["challenge"]["api_path"],
            "username": username,
            "password": password,
            "hint": hint,
            "proxy_url": proxy_url,
            "created_at": time.time(),
        }
        logger.info("account=%s code dispatched, token=%s hint=%s", username, token, hint)
        return {"type": "challenge", "token": token, "hint": hint}


def complete_challenge_login(token: str, code: str, account: Account, db: Session) -> Client:
    """Submits the verification code and finishes login. Saves session on success."""
    stored = PENDING_CHALLENGES.pop(token, None)
    if not stored:
        raise ValueError("Challenge expired or not found. Please try connecting again.")

    proxy_url = stored.get("proxy_url")
    cl = Client()
    if proxy_url:
        cl.set_proxy(proxy_url)
    cl.set_settings(stored["settings"])
    if proxy_url:
        cl.set_proxy(proxy_url)  # re-apply: set_settings can overwrite proxy

    challenge_url = stored["challenge_url"]
    cl._send_private_request(challenge_url, {"security_code": code})

    result = cl.last_json
    if result.get("action") != "close" or result.get("status") != "ok":
        raise ValueError("Incorrect or expired code. Please try again.")

    # Device is now approved — retry login to get full auth state
    time.sleep(1)
    cl2 = Client()
    if proxy_url:
        cl2.set_proxy(proxy_url)
    cl2.set_settings(cl.get_settings())
    if proxy_url:
        cl2.set_proxy(proxy_url)
    cl2.login(stored["username"], stored["password"])
    save_session(cl2, account, db)
    logger.info("account=%s challenge complete, session saved", stored["username"])
    return cl2


def login_by_sessionid(session_id: str, account: Account, db: Session, proxy_url: str = None) -> Client:
    """Logs in using an existing Instagram session cookie. Saves session on success."""
    # URL-decode in case the cookie value came URL-encoded from the browser
    decoded = unquote(session_id.strip())

    # Extract user_id from the session token (format: userid:token:0:hash)
    user_id_str = decoded.split(":")[0]
    if not user_id_str.isdigit():
        raise ValueError(f"Could not extract user_id from session ID: {decoded[:20]}...")

    cl = Client()
    if proxy_url:
        cl.set_proxy(proxy_url)

    # Inject session cookie. In instagrapi 2.x, user_id is a read-only property that reads
    # from cookie_dict["ds_user_id"], so we must set that cookie too.
    settings = cl.get_settings()
    settings["cookies"]["sessionid"] = decoded
    settings["cookies"]["ds_user_id"] = user_id_str
    cl.set_settings(settings)
    if proxy_url:
        cl.set_proxy(proxy_url)
    cl.username = account.username

    # Best-effort verification — log warning but don't block on failure.
    # Web-based sessionids may be rejected by the mobile API endpoint; the bot's
    # first poll will surface any real auth problems via account status.
    try:
        cl.direct_threads(amount=1)
        logger.info("account=%s session verified via direct_threads", account.username)
    except Exception as exc:
        logger.warning("account=%s session light-check failed (proceeding anyway): %s", account.username, exc)

    save_session(cl, account, db)
    logger.info("account=%s logged in via session ID", account.username)
    return cl


def poll_inbox(account: Account, db: Session) -> list:
    from services.anti_ban import handle_instagram_error
    try:
        cl = get_instagram_client(account)
        threads = cl.direct_threads(amount=20)
        save_session(cl, account, db)
        logger.debug("account=%s polled %d threads", account.username, len(threads))
        return threads
    except ChallengeRequired as exc:
        logger.warning("account=%s ChallengeRequired during poll", account.username)
        handle_instagram_error(account, db, "ChallengeRequired")
        raise
    except PleaseWaitFewMinutes as exc:
        logger.warning("account=%s rate-limited during poll", account.username)
        handle_instagram_error(account, db, "RateLimitError")
        raise
    except LoginRequired as exc:
        logger.warning("account=%s session expired during poll", account.username)
        handle_instagram_error(account, db, "LoginRequired")
        raise
    except Exception as exc:
        logger.error("account=%s unexpected error during poll: %s", account.username, exc, exc_info=True)
        handle_instagram_error(account, db, f"UnexpectedError:{type(exc).__name__}")
        raise


def send_dm(account: Account, thread_id: str, text: str, db: Session) -> bool:
    from services.anti_ban import get_typing_duration, handle_instagram_error
    try:
        cl = get_instagram_client(account)
        duration = get_typing_duration(len(text))
        logger.debug(
            "account=%s simulating typing for %.1fs before sending to thread=%s",
            account.username, duration, thread_id,
        )
        time.sleep(duration)
        cl.direct_send(text, thread_ids=[thread_id])
        save_session(cl, account, db)
        logger.info("account=%s sent DM to thread=%s (%d chars)", account.username, thread_id, len(text))
        return True
    except ChallengeRequired:
        logger.warning("account=%s ChallengeRequired while sending DM", account.username)
        handle_instagram_error(account, db, "ChallengeRequired")
        return False
    except PleaseWaitFewMinutes:
        logger.warning("account=%s rate-limited while sending DM", account.username)
        handle_instagram_error(account, db, "RateLimitError")
        return False
    except LoginRequired:
        logger.warning("account=%s session expired while sending DM", account.username)
        handle_instagram_error(account, db, "LoginRequired")
        return False
    except Exception as exc:
        logger.error(
            "account=%s unexpected error sending DM to thread=%s: %s",
            account.username, thread_id, exc, exc_info=True,
        )
        handle_instagram_error(account, db, f"UnexpectedError:{type(exc).__name__}")
        return False


def fetch_user_info(username: str, account: Account, db: Session) -> dict:
    """Returns dict with full_name and user_id. Falls back to username on any error."""
    try:
        cl = get_instagram_client(account)
        user_id = cl.user_id_from_username(username)
        user_info = cl.user_info(user_id)
        save_session(cl, account, db)
        full_name = user_info.full_name or username
        logger.debug("fetched info for @%s: full_name=%r user_id=%s", username, full_name, user_id)
        return {"user_id": str(user_id), "full_name": full_name}
    except Exception as exc:
        logger.warning("fetch_user_info failed for @%s: %s", username, exc)
        return {"user_id": None, "full_name": username}


def send_outbound_dm(account: Account, instagram_username: str, text: str, db: Session) -> Optional[str]:
    """
    Sends an initial DM to a user by username (starts new conversation).
    Returns thread_id on success, None on failure.
    """
    from services.anti_ban import get_typing_duration, handle_instagram_error
    try:
        cl = get_instagram_client(account)
        user_id = cl.user_id_from_username(instagram_username)
        duration = get_typing_duration(len(text))
        logger.debug(
            "account=%s simulating typing %.1fs before outbound DM to @%s",
            account.username, duration, instagram_username,
        )
        time.sleep(duration)
        thread = cl.direct_send(text, user_ids=[int(user_id)])
        save_session(cl, account, db)
        thread_id = str(thread.id)
        logger.info(
            "account=%s sent outbound DM to @%s thread=%s (%d chars)",
            account.username, instagram_username, thread_id, len(text),
        )
        return thread_id
    except ChallengeRequired:
        logger.warning("account=%s ChallengeRequired during outbound DM to @%s", account.username, instagram_username)
        handle_instagram_error(account, db, "ChallengeRequired")
        return None
    except PleaseWaitFewMinutes:
        logger.warning("account=%s rate-limited during outbound DM to @%s", account.username, instagram_username)
        handle_instagram_error(account, db, "RateLimitError")
        return None
    except LoginRequired:
        logger.warning("account=%s session expired during outbound DM", account.username)
        handle_instagram_error(account, db, "LoginRequired")
        return None
    except Exception as exc:
        logger.error(
            "account=%s unexpected error in send_outbound_dm to @%s: %s",
            account.username, instagram_username, exc, exc_info=True,
        )
        handle_instagram_error(account, db, f"OutboundError:{type(exc).__name__}")
        return None
