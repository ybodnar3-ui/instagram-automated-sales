import json
import logging
import time
from cryptography.fernet import InvalidToken
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, LoginRequired, PleaseWaitFewMinutes
from sqlalchemy.orm import Session
from config import cipher
from models.account import Account, BotStatus

logger = logging.getLogger(__name__)


def encrypt_session(session_dict: dict) -> str:
    return cipher.encrypt(json.dumps(session_dict).encode()).decode()


def decrypt_session(encrypted: str) -> dict:
    return json.loads(cipher.decrypt(encrypted.encode()).decode())


def get_instagram_client(account: Account) -> Client:
    cl = Client()
    if account.session_data:
        try:
            session = decrypt_session(account.session_data)
            cl.set_settings(session)
        except (InvalidToken, json.JSONDecodeError, Exception) as exc:
            logger.error(
                "account=%s could not decrypt session, will require fresh login: %s",
                account.username, exc,
            )
            # Return a clean client; next login attempt will overwrite session
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
