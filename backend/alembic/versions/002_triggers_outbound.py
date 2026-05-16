"""Add triggers and outbound_targets tables; outbound columns to bot_config

Revision ID: 002
Revises: 001
Create Date: 2026-05-16

"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "triggers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword", sa.String(200), nullable=False),
        sa.Column("response_template", sa.Text, nullable=False),
        sa.Column("use_ai_followup", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_triggers_id", "triggers", ["id"])
    op.create_index("ix_triggers_account_id", "triggers", ["account_id"])

    op.create_table(
        "outbound_targets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instagram_username", sa.String(100), nullable=False),
        sa.Column("initial_message", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "sent", "failed", "skipped", name="outboundstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outbound_targets_id", "outbound_targets", ["id"])
    op.create_index("ix_outbound_targets_account_id", "outbound_targets", ["account_id"])
    op.create_index("ix_outbound_targets_status", "outbound_targets", ["status"])

    op.add_column("bot_config", sa.Column("outbound_daily_limit", sa.Integer, nullable=False, server_default="5"))
    op.add_column("bot_config", sa.Column("outbound_default_message", sa.Text, nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("bot_config", "outbound_default_message")
    op.drop_column("bot_config", "outbound_daily_limit")
    op.drop_table("outbound_targets")
    op.execute("DROP TYPE IF EXISTS outboundstatus")
    op.drop_table("triggers")
