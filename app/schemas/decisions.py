"""Decisões produzidas por agentes e transições de fluxo."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.commands import Command


class Transition(BaseModel):
    type: Literal["stay", "complete", "cancel", "switch"]
    target_flow: str | None = None


class AgentDecision(BaseModel):
    """Envelope único; não concede autoridade para executar o comando."""

    message: str | None = None
    command: Command | None = None
    transition: Transition | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

