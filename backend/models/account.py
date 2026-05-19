import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Enum as SAEnum
from database import Base


class BotStatus(enum.Enum):
    active = "active"
    paused = "paused"
    error = "error"


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    session_data = Column(Text, nullable=True)  # Fernet-encrypted JSON
    is_active = Column(Boolean, default=True, nullable=False)
    daily_limit = Column(Integer, default=80, nullable=False)
    messages_today = Column(Integer, default=0, nullable=False)
    last_reset_date = Column(DateTime(timezone=True), nullable=True)
    bot_status = Column(SAEnum(BotStatus), default=BotStatus.active, nullable=False, index=True)
    pause_reason = Column(String(200), nullable=True)
    proxy_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
