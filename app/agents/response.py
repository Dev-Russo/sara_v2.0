"""Seam do ResponseAgent, grounded no HarnessResult."""

from typing import Protocol

from app.schemas.events import ExecutionContext
from app.schemas.results import HarnessResult, ResponseDecision


class ResponseAgent(Protocol):
    async def respond(
        self,
        result: HarnessResult,
        context: ExecutionContext,
    ) -> ResponseDecision:
        """Verbaliza apenas efeitos presentes no resultado estruturado."""
