from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models.account import Account, BotStatus
from models.stats import BotConfig

router = APIRouter()


class ConfigUpdate(BaseModel):
    business_name: Optional[str] = None
    service_description: Optional[str] = None
    price_info: Optional[str] = None
    objections_script: Optional[str] = None
    max_messages_per_day: Optional[int] = None
    min_delay_sec: Optional[float] = None
    max_delay_sec: Optional[float] = None
    llm_model: Optional[str] = None
    warmup_mode: Optional[bool] = None


@router.post("/bot/{account_id}/pause")
def pause_bot(account_id: int, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.bot_status = BotStatus.paused
    account.pause_reason = "manual"
    db.commit()
    return {"status": "paused"}


@router.post("/bot/{account_id}/resume")
def resume_bot(account_id: int, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.bot_status = BotStatus.active
    account.pause_reason = None
    db.commit()
    return {"status": "active"}


@router.get("/bot/{account_id}/status")
def get_bot_status(account_id: int, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    config = db.query(BotConfig).filter(BotConfig.account_id == account_id).first()
    from services.anti_ban import get_effective_daily_limit
    return {
        "status": account.bot_status.value,
        "pause_reason": account.pause_reason,
        "messages_today": account.messages_today,
        "daily_limit": get_effective_daily_limit(account, config),
        "username": account.username,
    }


@router.put("/bot/{account_id}/config")
def update_config(account_id: int, payload: ConfigUpdate, db: Session = Depends(get_db)):
    config = db.query(BotConfig).filter(BotConfig.account_id == account_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(config, field, value)
    db.commit()
    return {"status": "updated"}


@router.get("/bot/{account_id}/config")
def get_config(account_id: int, db: Session = Depends(get_db)):
    config = db.query(BotConfig).filter(BotConfig.account_id == account_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    return {
        "business_name": config.business_name,
        "service_description": config.service_description,
        "price_info": config.price_info,
        "objections_script": config.objections_script,
        "max_messages_per_day": config.max_messages_per_day,
        "min_delay_sec": config.min_delay_sec,
        "max_delay_sec": config.max_delay_sec,
        "llm_model": config.llm_model,
        "warmup_mode": config.warmup_mode,
    }
