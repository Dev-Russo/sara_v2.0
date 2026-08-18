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
        """Executa um comando cujo handler foi registrado explicitamente."""

        handler = self._registry.get(command.type)
        if handler is None:
            return HarnessResult(
                status="rejected",
                command_id=command.command_id,
                command_type=command.type,
                error_code="COMMAND_NOT_SUPPORTED",
            )
        return await handler(command, context)

    async def resolve_confirmation(
        self,
        confirmation_id: UUID,
        context: ExecutionContext,
        decision: str,
    ) -> HarnessResult:
        """Retoma um snapshot persistido sem passar pelo Supervisor."""

        raise NotImplementedError("confirmation resolution is not implemented yet")
