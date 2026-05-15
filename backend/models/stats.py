from sqlalchemy import Column, Integer, String, Float, Boolean, Date, ForeignKey, Text, UniqueConstraint
from database import Base


class BotConfig(Base):
    __tablename__ = "bot_config"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), unique=True, nullable=False)
    system_prompt = Column(Text, default="", nullable=False)
    business_name = Column(String(200), default="", nullable=False)
    service_description = Column(Text, default="", nullable=False)
    price_info = Column(String(500), default="", nullable=False)
    objections_script = Column(Text, default="", nullable=False)
    max_messages_per_day = Column(Integer, default=80, nullable=False)
    min_delay_sec = Column(Float, default=8.0, nullable=False)
    max_delay_sec = Column(Float, default=25.0, nullable=False)
    llm_model = Column(String(100), default="claude-haiku-3-5-20251001", nullable=False)
    warmup_mode = Column(Boolean, default=True, nullable=False)


class DailyStats(Base):
    __tablename__ = "daily_stats"
    __table_args__ = (UniqueConstraint("account_id", "date", name="uq_account_date"),)

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    messages_sent = Column(Integer, default=0, nullable=False)
    messages_received = Column(Integer, default=0, nullable=False)
    new_conversations = Column(Integer, default=0, nullable=False)
    conversions = Column(Integer, default=0, nullable=False)
    tokens_used = Column(Integer, default=0, nullable=False)
