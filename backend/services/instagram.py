import json
import time
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, LoginRequired, PleaseWaitFewMinutes
from sqlalchemy.orm import Session
from config import cipher
from models.account import Account, BotStatus


def encrypt_session(session_dict: dict) -> str:
    return cipher.encrypt(json.dumps(session_dict).encode()).decode()


def decrypt_session(encrypted: str) -> dict:
    return json.loads(cipher.decrypt(encrypted.encode()).decode())


def get_instagram_client(account: Account) -> Client:
    cl = Client()
    if account.session_data:
        session = decrypt_session(account.session_data)
        cl.set_settings(session)
    return cl


def save_session(cl: Client, account: Account, db: Session) -> None:
    account.session_data = encrypt_session(cl.get_settings())
    db.commit()


def login_and_save(username: str, password: str, account: Account, db: Session) -> Client:
    cl = Client()
    cl.login(username, password)
    save_session(cl, account, db)
    return cl


def poll_inbox(account: Account, db: Session) -> list:
    from services.anti_ban import handle_instagram_error
    try:
        cl = get_instagram_client(account)
        threads = cl.direct_threads(amount=20)
        save_session(cl, account, db)
        return threads
    except ChallengeRequired as exc:
        handle_instagram_error(account, db, "ChallengeRequired")
        raise
    except PleaseWaitFewMinutes as exc:
        handle_instagram_error(account, db, "RateLimitError")
        raise
    except LoginRequired as exc:
        handle_instagram_error(account, db, "LoginRequired")
        raise


def send_dm(account: Account, thread_id: str, text: str, db: Session) -> bool:
    from services.anti_ban import get_typing_duration, handle_instagram_error
    try:
        cl = get_instagram_client(account)
        duration = get_typing_duration(len(text))
        time.sleep(duration)
        cl.direct_send(text, thread_ids=[thread_id])
        save_session(cl, account, db)
        return True
    except ChallengeRequired:
        handle_instagram_error(account, db, "ChallengeRequired")
        return False
    except PleaseWaitFewMinutes:
        handle_instagram_error(account, db, "RateLimitError")
        return False
    except LoginRequired:
        handle_instagram_error(account, db, "LoginRequired")
        return False
