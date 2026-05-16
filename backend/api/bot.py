from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from database import get_db
from models.account import Account, BotStatus
from models.stats import BotConfig

router = APIRouter()

ALLOWED_MODELS = {"claude-haiku-3-5-20251001", "claude-sonnet-4-6"}


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
    outbound_daily_limit: Optional[int] = None
    outbound_default_message: Optional[str] = None

    @field_validator("llm_model")
    @classmethod
    def validate_llm_model(cls, v):
        if v is not None and v not in ALLOWED_MODELS:
            raise ValueError(f"llm_model must be one of: {', '.join(sorted(ALLOWED_MODELS))}")
        return v

    @field_validator("max_messages_per_day")
    @classmethod
    def validate_daily_limit(cls, v):
        if v is not None and not (1 <= v <= 200):
            raise ValueError("max_messages_per_day must be between 1 and 200")
        return v

    @field_validator("min_delay_sec", "max_delay_sec")
    @classmethod
    def validate_delay(cls, v):
        if v is not None and v < 1:
            raise ValueError("delay must be at least 1 second")
        return v

    @field_validator("outbound_daily_limit")
    @classmethod
    def validate_outbound_limit(cls, v):
        if v is not None and not (0 <= v <= 50):
            raise ValueError("outbound_daily_limit must be between 0 and 50")
        return v

    def model_post_init(self, __context) -> None:
        if self.min_delay_sec is not None and self.max_delay_sec is not None:
            if self.min_delay_sec > self.max_delay_sec:
                raise ValueError("min_delay_sec must not exceed max_delay_sec")


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
        "outbound_daily_limit": config.outbound_daily_limit,
        "outbound_default_message": config.outbound_default_message,
    }
