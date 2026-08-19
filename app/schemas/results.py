"""Resultados estruturados de execução."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.decisions import Transition

HarnessStatus = Literal[
    "executed",
    "awaiting_confirmation",
    "awaiting_selection",
    "rejected",
    "failed",
    "duplicate",
]


class HarnessResult(BaseModel):
    """Fonte de verdade para o Graph e para o ResponseAgent."""

    status: HarnessStatus
    command_id: UUID
    command_type: str
    message: str | None = None
    effect: dict[str, object] | None = None
    confirmation_id: UUID | None = None
    error_code: str | None = None


class ResponseDecision(BaseModel):
    message: str
    transition: Transition | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
