"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-15

"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("session_data", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("daily_limit", sa.Integer, nullable=False, server_default="80"),
        sa.Column("messages_today", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_reset_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "bot_status",
            sa.Enum("active", "paused", "error", name="botstatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("pause_reason", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_accounts_id", "accounts", ["id"])
    op.create_index("ix_accounts_username", "accounts", ["username"])
    op.create_index("ix_accounts_bot_status", "accounts", ["bot_status"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instagram_thread_id", sa.String(100), nullable=False),
        sa.Column("interlocutor_username", sa.String(100), nullable=True),
        sa.Column(
            "stage",
            sa.Enum("new", "in_progress", "converted", "dead", name="convstage"),
            nullable=False,
            server_default="new",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("messages_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_converted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("bot_active", sa.Boolean, nullable=False, server_default="true"),
        sa.UniqueConstraint("account_id", "instagram_thread_id", name="uq_account_thread"),
    )
    op.create_index("ix_conversations_id", "conversations", ["id"])
    op.create_index("ix_conversations_account_id", "conversations", ["account_id"])
    op.create_index("ix_conversations_stage", "conversations", ["stage"])
    op.create_index("ix_conversations_last_message_at", "conversations", ["last_message_at"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("incoming", "outgoing", name="direction"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delay_seconds", sa.Float, nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
    )
    op.create_index("ix_messages_id", "messages", ["id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_sent_at", "messages", ["sent_at"])

    op.create_table(
        "bot_config",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("system_prompt", sa.Text, nullable=False, server_default=""),
        sa.Column("business_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("service_description", sa.Text, nullable=False, server_default=""),
        sa.Column("price_info", sa.String(500), nullable=False, server_default=""),
        sa.Column("objections_script", sa.Text, nullable=False, server_default=""),
        sa.Column("max_messages_per_day", sa.Integer, nullable=False, server_default="80"),
        sa.Column("min_delay_sec", sa.Float, nullable=False, server_default="8.0"),
        sa.Column("max_delay_sec", sa.Float, nullable=False, server_default="25.0"),
        sa.Column("llm_model", sa.String(100), nullable=False, server_default="claude-haiku-3-5-20251001"),
        sa.Column("warmup_mode", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_index("ix_bot_config_id", "bot_config", ["id"])

    op.create_table(
        "daily_stats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("messages_sent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("messages_received", sa.Integer, nullable=False, server_default="0"),
        sa.Column("new_conversations", sa.Integer, nullable=False, server_default="0"),
        sa.Column("conversions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_used", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("account_id", "date", name="uq_account_date"),
    )
    op.create_index("ix_daily_stats_id", "daily_stats", ["id"])
    op.create_index("ix_daily_stats_account_id", "daily_stats", ["account_id"])
    op.create_index("ix_daily_stats_date", "daily_stats", ["date"])


def downgrade() -> None:
    op.drop_table("daily_stats")
    op.drop_table("bot_config")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("accounts")
    op.execute("DROP TYPE IF EXISTS botstatus")
    op.execute("DROP TYPE IF EXISTS convstage")
    op.execute("DROP TYPE IF EXISTS direction")
