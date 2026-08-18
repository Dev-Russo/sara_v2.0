"""Catálogo explícito de handlers de comandos."""

from collections.abc import Awaitable, Callable

from app.schemas.commands import Command
from app.schemas.events import ExecutionContext
from app.schemas.results import HarnessResult

CommandHandler = Callable[[Command, ExecutionContext], Awaitable[HarnessResult]]


class CommandRegistry:
    """Registro pequeno e explícito; não há fallback para handlers genéricos."""

    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, command_type: str, handler: CommandHandler) -> None:
        if command_type in self._handlers:
            raise ValueError(f"command handler already registered: {command_type}")
        self._handlers[command_type] = handler

    def get(self, command_type: str) -> CommandHandler | None:
        return self._handlers.get(command_type)

