import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, Enum as SAEnum, Text
from database import Base


class Direction(enum.Enum):
    incoming = "incoming"
    outgoing = "outgoing"


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    direction = Column(SAEnum(Direction), nullable=False)
    content = Column(Text, nullable=False)
    sent_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    delay_seconds = Column(Float, nullable=True)
    tokens_used = Column(Integer, nullable=True)
