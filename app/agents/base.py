"""Seam comum dos agentes."""

from typing import Protocol

from app.schemas.decisions import AgentDecision
from app.schemas.events import ExecutionContext, MessageEvent


class Agent(Protocol):
    async def decide(self, event: MessageEvent, context: ExecutionContext) -> AgentDecision:
        """Interpreta o evento sem executar efeitos colaterais."""

