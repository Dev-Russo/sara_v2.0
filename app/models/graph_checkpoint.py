"""Checkpoint durável do estado de continuação do Graph."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class GraphCheckpoint(TimestampMixin, Base):
    __tablename__ = "graph_checkpoints"
    __table_args__ = (
        Index(
            "ix_graph_checkpoints_user_updated_at",
            "user_id",
            "updated_at",
        ),
    )

    graph_thread_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    state_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
