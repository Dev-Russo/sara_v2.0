"""Eventos internos independentes dos SDKs de transporte."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

EventSource = Literal["telegram", "scheduler", "cli", "test"]


class ExecutionContext(BaseModel):
    """Contexto criado na borda confiável; o agente não controla o user_id."""

    user_id: UUID
    flow_id: UUID | None = None
    graph_thread_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    source: EventSource


class MessageEvent(BaseModel):
    event_id: str = Field(min_length=1)
    user_id: UUID
    text: str
    received_at: datetime
    source: EventSource
    metadata: dict[str, object] = Field(default_factory=dict)


class ConfirmationEvent(BaseModel):
    confirmation_id: UUID
    user_id: UUID
    decision: Literal["confirm", "cancel"]
    received_at: datetime
    source: Literal["telegram", "cli", "test"]
