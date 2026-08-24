"""Add persisted Telegram update deduplication.

Revision ID: 0003_processed_updates
Revises: 0002_confirmation_requests
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_processed_updates"
down_revision: str | None = "0002_confirmation_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processed_updates",
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("telegram_chat_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("update_id"),
    )
    op.create_index(
        "ix_processed_updates_user_received_at",
        "processed_updates",
        ["user_id", "received_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_processed_updates_user_received_at",
        table_name="processed_updates",
    )
    op.drop_table("processed_updates")
