import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
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


@router.post("/accounts", status_code=201)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    from services.instagram import login_and_save

    username = payload.username.lower().strip()

    if db.query(Account).filter(Account.username == username).first():
        raise HTTPException(status_code=400, detail="Account already exists")

    account = Account(username=username, created_at=datetime.now(timezone.utc))
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account already exists (concurrent request)")
    db.refresh(account)

    try:
        login_and_save(payload.username, payload.password, account, db)
    except Exception as exc:
        logger.error("account=%s Instagram login failed: %s", username, exc)
        db.delete(account)
        db.commit()
        raise HTTPException(status_code=400, detail=f"Instagram login failed: {exc}")

    config = BotConfig(
        account_id=account.id,
        business_name=payload.business_name,
        service_description=payload.service_description,
        price_info=payload.price_info,
        objections_script=payload.objections_script,
    )
    db.add(config)
    db.commit()
    logger.info("account=%s created and bot configured", username)

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
