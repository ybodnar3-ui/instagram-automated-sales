import random
from datetime import datetime, timezone, date
from typing import Optional
from sqlalchemy.orm import Session
from models.account import Account, BotStatus
from models.stats import BotConfig


def get_warmup_limit(account: Account) -> int:
    days_old = (datetime.now(timezone.utc) - account.created_at).days
    if days_old <= 3:
        return 15
    if days_old <= 7:
        return 30
    if days_old <= 14:
        return 50
    return 80


def get_human_delay(message_length: int) -> float:
    base_delay = random.uniform(8, 25)
    reading_time = message_length * 0.03
    typing_time = random.uniform(3, 12)
    return base_delay + reading_time + typing_time


def get_typing_duration(response_length: int) -> float:
    return response_length * random.uniform(0.05, 0.1)


def get_effective_daily_limit(account: Account, config: Optional[BotConfig]) -> int:
    if config is None:
        return account.daily_limit
    if config.warmup_mode:
        warmup_limit = get_warmup_limit(account)
        return min(warmup_limit, config.max_messages_per_day)
    return config.max_messages_per_day


def check_and_reset_daily_limit(account: Account, db: Session) -> None:
    today = date.today()
    last_reset = account.last_reset_date
    if last_reset is None:
        # Never been reset — treat as already initialized for today (no reset needed)
        return

    if hasattr(last_reset, 'date'):
        last_reset_date = last_reset.date()
    elif isinstance(last_reset, date):
        last_reset_date = last_reset
    else:
        last_reset_date = None

    if last_reset_date is not None and last_reset_date < today:
        account.messages_today = 0
        account.last_reset_date = datetime.now(timezone.utc)
        if account.bot_status == BotStatus.paused and account.pause_reason == "daily_limit":
            account.bot_status = BotStatus.active
            account.pause_reason = None
        db.commit()


def can_send_message(account: Account, config: Optional[BotConfig], db: Session) -> bool:
    check_and_reset_daily_limit(account, db)
    if account.bot_status != BotStatus.active:
        return False
    limit = get_effective_daily_limit(account, config)
    return account.messages_today < limit


def pause_for_daily_limit(account: Account, db: Session) -> None:
    account.bot_status = BotStatus.paused
    account.pause_reason = "daily_limit"
    db.commit()


def handle_instagram_error(account: Account, db: Session, error_type: str) -> None:
    account.bot_status = BotStatus.error
    account.pause_reason = f"instagram_error:{error_type}"
    db.commit()
