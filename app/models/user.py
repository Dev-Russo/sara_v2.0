"""Modelo User."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/Sao_Paulo")
    telegram_chat_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    tasks: Mapped[list[Task]] = relationship(back_populates="user", cascade="all, delete-orphan")
    command_executions: Mapped[list[CommandExecution]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    confirmation_requests: Mapped[list[ConfirmationRequest]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


from app.models.command_execution import CommandExecution  # noqa: E402  # isort: skip
from app.models.confirmation_request import ConfirmationRequest  # noqa: E402  # isort: skip
from app.models.task import Task  # noqa: E402  # isort: skip
