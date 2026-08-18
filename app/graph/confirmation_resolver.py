"""Retomada determinística de uma confirmação persistida."""

from typing import Protocol
from uuid import UUID

from app.schemas.events import ExecutionContext
from app.schemas.results import HarnessResult


class ConfirmationResolver(Protocol):
    async def resolve(
        self,
        confirmation_id: UUID,
        context: ExecutionContext,
        decision: str,
    ) -> HarnessResult:
        """Resolve somente o snapshot persistido; não reclassifica a mensagem."""

