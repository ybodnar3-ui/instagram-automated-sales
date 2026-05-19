import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database import get_db
from models.account import Account, BotStatus
from models.stats import BotConfig

logger = logging.getLogger(__name__)
router = APIRouter()


class AccountCreate(BaseModel):
    username: str
    password: str
    business_name: str
    service_description: str
    price_info: str
    objections_script: str
    proxy_url: str = ""


class ChallengeVerifyPayload(BaseModel):
    token: str
    code: str


class SessionLoginPayload(BaseModel):
    username: str
    session_id: str
    business_name: str = ""
    service_description: str = ""
    price_info: str = ""
    objections_script: str = ""
    proxy_url: str = ""


def _create_config(account_id: int, payload_dict: dict, db: Session) -> None:
    config = BotConfig(
        account_id=account_id,
        business_name=payload_dict.get("business_name", ""),
        service_description=payload_dict.get("service_description", ""),
        price_info=payload_dict.get("price_info", ""),
        objections_script=payload_dict.get("objections_script", ""),
    )
    db.add(config)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.error("account_id=%s failed to create BotConfig, rolling back", account_id, exc_info=True)
        raise


@router.post("/accounts")
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    from services.instagram import begin_challenge_login, PENDING_CHALLENGES

    username = payload.username.lower().strip()

    if db.query(Account).filter(Account.username == username).first():
        raise HTTPException(status_code=400, detail="Account already exists")

    proxy_url = payload.proxy_url.strip() or None
    account = Account(username=username, created_at=datetime.now(timezone.utc), proxy_url=proxy_url)
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account already exists (concurrent request)")
    db.refresh(account)

    try:
        result = begin_challenge_login(payload.username, payload.password, proxy_url=proxy_url)
    except Exception as exc:
        logger.error("account=%s Instagram login failed: %s", username, exc, exc_info=True)
        db.delete(account)
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Instagram login failed. Check username/password and try again.",
        )

    if result["type"] == "challenge":
        # Store the full payload so we can create the account after code verification
        token = result["token"]
        PENDING_CHALLENGES[token]["account_id_temp"] = account.id
        PENDING_CHALLENGES[token]["payload"] = payload.model_dump()
        # Remove the incomplete account — it gets re-created in /challenge/verify
        db.delete(account)
        db.commit()
        return JSONResponse(
            status_code=200,
            content={
                "status": "challenge_required",
                "token": token,
                "hint": result["hint"],
            },
        )

    # Direct success
    from services.instagram import save_session
    save_session(result["cl"], account, db)
    _create_config(account.id, payload.model_dump(), db)
    logger.info("account=%s created and bot configured", username)
    return JSONResponse(
        status_code=201,
        content={"id": account.id, "username": account.username, "status": account.bot_status.value},
    )


@router.post("/accounts/challenge/verify", status_code=201)
def verify_challenge(payload: ChallengeVerifyPayload, db: Session = Depends(get_db)):
    from services.instagram import PENDING_CHALLENGES, complete_challenge_login

    stored = PENDING_CHALLENGES.get(payload.token)
    if not stored:
        raise HTTPException(status_code=400, detail="Challenge expired. Please start over.")

    orig_payload = stored.get("payload", {})
    username = orig_payload.get("username", "").lower().strip()

    if not username:
        raise HTTPException(status_code=400, detail="Challenge data is corrupt. Please start over.")

    if db.query(Account).filter(Account.username == username).first():
        raise HTTPException(status_code=400, detail="Account already exists")

    proxy_url = orig_payload.get("proxy_url", "") or None
    account = Account(username=username, created_at=datetime.now(timezone.utc), proxy_url=proxy_url)
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account already exists")
    db.refresh(account)

    try:
        complete_challenge_login(payload.token, payload.code, account, db)
    except ValueError as exc:
        db.delete(account)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("challenge verify failed: %s", exc, exc_info=True)
        db.delete(account)
        db.commit()
        raise HTTPException(status_code=400, detail="Verification failed. Please try again.")

    _create_config(account.id, orig_payload, db)
    logger.info("account=%s created via challenge flow", username)
    return {"id": account.id, "username": account.username, "status": account.bot_status.value}


@router.post("/accounts/session-login", status_code=201)
def session_login(payload: SessionLoginPayload, db: Session = Depends(get_db)):
    from services.instagram import login_by_sessionid

    username = payload.username.lower().strip()

    if db.query(Account).filter(Account.username == username).first():
        raise HTTPException(status_code=400, detail="Account already exists")

    proxy_url = payload.proxy_url.strip() or None
    account = Account(username=username, created_at=datetime.now(timezone.utc), proxy_url=proxy_url)
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account already exists")
    db.refresh(account)

    try:
        login_by_sessionid(payload.session_id.strip(), account, db, proxy_url=proxy_url)
    except Exception as exc:
        logger.error("account=%s session login failed: %s", username, exc, exc_info=True)
        db.delete(account)
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Session ID login failed. Make sure the session ID is correct and not expired.",
        )

    _create_config(account.id, payload.model_dump(), db)
    logger.info("account=%s created via session ID login", username)
    return {"id": account.id, "username": account.username, "status": account.bot_status.value}


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db)):
    accounts = db.query(Account).all()
    return [
        {
            "id": a.id,
            "username": a.username,
            "status": a.bot_status.value,
            "messages_today": a.messages_today,
            "daily_limit": a.daily_limit,
            "created_at": a.created_at.isoformat(),
        }
        for a in accounts
    ]


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    username = account.username
    db.delete(account)
    db.commit()
    logger.info("account=%s deleted", username)
    return {"status": "deleted"}
