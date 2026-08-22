"""Add persisted confirmation requests for destructive commands.

Revision ID: 0002_confirmation_requests
Revises: 0001_task_core
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_confirmation_requests"
down_revision: str | None = "0001_task_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "confirmation_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("command_type", sa.String(length=100), nullable=False),
        sa.Column("payload_snapshot", sa.JSON(), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["command_executions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_confirmation_requests_user_status_expires_at",
        "confirmation_requests",
        ["user_id", "status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_confirmation_requests_user_status_expires_at",
        table_name="confirmation_requests",
    )
    op.drop_table("confirmation_requests")
