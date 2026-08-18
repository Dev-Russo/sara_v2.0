"""Handlers que adaptam casos de uso para o contrato do Harness."""

from collections.abc import Awaitable, Callable

from app.harness.registry import CommandRegistry
from app.schemas.commands import Command, TasksCreateCommand
from app.schemas.events import ExecutionContext
from app.schemas.results import HarnessResult
from app.services.tasks import TaskService


def register_task_handlers(registry: CommandRegistry, task_service: TaskService) -> None:
    """Registra somente comandos de tarefa implementados nesta fatia."""

    async def create_task(command: Command, context: ExecutionContext) -> HarnessResult:
        if not isinstance(command, TasksCreateCommand):
            raise TypeError("tasks.create handler received an incompatible command")

        outcome = await task_service.create_task(context, command.payload)
        task = outcome.task
        return HarnessResult(
            status="duplicate" if outcome.duplicate else "executed",
            command_id=command.command_id,
            command_type=command.type,
            effect={
                "kind": "task_created",
                "task_id": str(task.id),
                "title": task.title,
                "priority": task.priority,
            },
        )

    handler: Callable[[Command, ExecutionContext], Awaitable[HarnessResult]] = create_task
    registry.register("tasks.create", handler)
