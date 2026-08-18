"""Interface e composição inicial do Harness."""

from uuid import UUID

from app.harness.registry import CommandRegistry
from app.schemas.commands import Command
from app.schemas.events import ExecutionContext
from app.schemas.results import HarnessResult


class Harness:
    """Módulo profundo que concentrará policy, idempotência e execução."""

    def __init__(self, registry: CommandRegistry) -> None:
        self._registry = registry

    async def handle(self, command: Command, context: ExecutionContext) -> HarnessResult:
        """Executa um comando validado; o pipeline será implementado por fatias."""

        raise NotImplementedError("Harness pipeline is not implemented yet")

    async def resolve_confirmation(
        self,
        confirmation_id: UUID,
        context: ExecutionContext,
        decision: str,
    ) -> HarnessResult:
        """Retoma um snapshot persistido sem passar pelo Supervisor."""

        raise NotImplementedError("confirmation resolution is not implemented yet")

