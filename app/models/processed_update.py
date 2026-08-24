"""Persisted Telegram update used for ingress deduplication."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ProcessedUpdate(TimestampMixin, Base):
    __tablename__ = "processed_updates"
    __table_args__ = (
        Index(
            "ix_processed_updates_user_received_at",
            "user_id",
            "received_at",
        ),
    )

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    telegram_chat_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="received")
