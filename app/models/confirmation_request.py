"""Modelo ConfirmationRequest, snapshot persistido do Human-in-the-Loop."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ConfirmationRequest(TimestampMixin, Base):
    __tablename__ = "confirmation_requests"
    __table_args__ = (
        Index(
            "ix_confirmation_requests_user_status_expires_at",
            "user_id",
            "status",
            "expires_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("command_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    command_id: Mapped[UUID] = mapped_column(nullable=False)
    command_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="confirmation_requests")


from app.models.user import User  # noqa: E402  # isort: skip
