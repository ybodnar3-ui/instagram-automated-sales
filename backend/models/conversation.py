import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum as SAEnum
from database import Base


class ConvStage(enum.Enum):
    new = "new"
    in_progress = "in_progress"
    converted = "converted"
    dead = "dead"


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    instagram_thread_id = Column(String(100), nullable=False)
    interlocutor_username = Column(String(100), nullable=True)
    stage = Column(SAEnum(ConvStage), default=ConvStage.new, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_message_at = Column(DateTime, nullable=True)
    messages_count = Column(Integer, default=0, nullable=False)
    is_converted = Column(Boolean, default=False, nullable=False)
    bot_active = Column(Boolean, default=True, nullable=False)  # False = human takeover
