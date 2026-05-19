"""Add proxy_url to accounts

Revision ID: 003
Revises: 002
Create Date: 2026-05-18

"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("proxy_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "proxy_url")
