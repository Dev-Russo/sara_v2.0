"""Handlers que adaptam casos de uso para o contrato do Harness."""

from collections.abc import Awaitable, Callable

from app.harness.registry import CommandRegistry
from app.schemas.commands import Command, TasksCreateCommand, TasksListCommand
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

    async def list_tasks(command: Command, context: ExecutionContext) -> HarnessResult:
        if not isinstance(command, TasksListCommand):
            raise TypeError("tasks.list handler received an incompatible command")

        outcome = await task_service.list_tasks(context, command.payload)
        return HarnessResult(
            status="executed",
            command_id=command.command_id,
            command_type=command.type,
            effect={
                "kind": "tasks_listed",
                "items": [item.model_dump(mode="json") for item in outcome.items],
                "total": outcome.total,
                "filters": command.payload.model_dump(mode="json"),
            },
        )

    handler: Callable[[Command, ExecutionContext], Awaitable[HarnessResult]] = create_task
    registry.register("tasks.create", handler)
    list_handler: Callable[[Command, ExecutionContext], Awaitable[HarnessResult]] = list_tasks
    registry.register("tasks.list", list_handler)
