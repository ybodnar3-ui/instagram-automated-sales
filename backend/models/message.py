import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SAEnum, Text
from database import Base


class Direction(enum.Enum):
    incoming = "incoming"
    outgoing = "outgoing"


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    direction = Column(SAEnum(Direction), nullable=False)
    content = Column(Text, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    delay_seconds = Column(Float, nullable=True)   # only for outgoing
    tokens_used = Column(Integer, nullable=True)    # only for outgoing
