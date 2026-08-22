"""Interface e composição inicial do Harness."""

from typing import Protocol
from uuid import UUID

from app.harness.policies import requires_confirmation
from app.harness.registry import CommandRegistry
from app.schemas.commands import Command
from app.schemas.events import ExecutionContext
from app.schemas.results import HarnessResult


class ConfirmationResolver(Protocol):
    async def resolve(
        self,
        confirmation_id: UUID,
        context: ExecutionContext,
        decision: str,
    ) -> HarnessResult:
        """Resolve um snapshot persistido sem nova interpretação do agente."""


class Harness:
    """Módulo profundo que concentrará policy, idempotência e execução."""

    def __init__(
        self,
        registry: CommandRegistry,
        *,
        confirmation_resolver: ConfirmationResolver | None = None,
    ) -> None:
        self._registry = registry
        self._confirmation_resolver = confirmation_resolver

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
        result = await handler(command, context)
        if requires_confirmation(command.type) and result.status == "executed":
            return HarnessResult(
                status="rejected",
                command_id=command.command_id,
                command_type=command.type,
                error_code="CONFIRMATION_REQUIRED",
            )
        return result

    async def resolve_confirmation(
        self,
        confirmation_id: UUID,
        context: ExecutionContext,
        decision: str,
    ) -> HarnessResult:
        """Retoma um snapshot persistido sem passar pelo Supervisor."""

        if self._confirmation_resolver is None:
            return HarnessResult(
                status="rejected",
                command_id=confirmation_id,
                command_type="confirmation",
                error_code="CONFIRMATION_NOT_SUPPORTED",
            )
        return await self._confirmation_resolver.resolve(
            confirmation_id,
            context,
            decision,
        )
