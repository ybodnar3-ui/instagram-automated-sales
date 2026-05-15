import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum as SAEnum, UniqueConstraint
from database import Base


class ConvStage(enum.Enum):
    new = "new"
    in_progress = "in_progress"
    converted = "converted"
    dead = "dead"


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("account_id", "instagram_thread_id", name="uq_account_thread"),)

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    instagram_thread_id = Column(String(100), nullable=False)
    interlocutor_username = Column(String(100), nullable=True)
    stage = Column(SAEnum(ConvStage), default=ConvStage.new, nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)
    messages_count = Column(Integer, default=0, nullable=False)
    is_converted = Column(Boolean, default=False, nullable=False)
    bot_active = Column(Boolean, default=True, nullable=False)
