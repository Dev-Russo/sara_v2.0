"""Estado persistido de entregas Telegram associadas a updates recebidos."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TelegramDelivery(TimestampMixin, Base):
    __tablename__ = "telegram_deliveries"
    __table_args__ = (
        Index(
            "ix_telegram_deliveries_user_status",
            "user_id",
            "status",
        ),
    )

    delivery_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    update_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("processed_updates.update_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    chat_id: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    reply_markup: Mapped[dict[str, object] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
