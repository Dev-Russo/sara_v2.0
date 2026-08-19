"""Handlers que adaptam casos de uso para o contrato do Harness."""

from collections.abc import Awaitable, Callable

from app.harness.registry import CommandRegistry
from app.schemas.commands import (
    Command,
    TasksCompleteByIdCommand,
    TasksCompleteCommand,
    TasksCreateCommand,
    TasksListCommand,
)
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

    async def complete_task_by_query(
        command: Command,
        context: ExecutionContext,
    ) -> HarnessResult:
        """Resolve uma referência textual antes de concluir a tarefa.

        Este é o primeiro passo do fluxo: a busca trata zero, um ou vários
        candidatos. Quando há ambiguidade, o resultado fica em
        ``awaiting_selection`` para o usuário escolher uma opção.
        """
        if not isinstance(command, TasksCompleteCommand):
            raise TypeError("tasks.complete handler received an incompatible command")

        outcome = await task_service.complete_task_by_query(context, command.payload.query)
        if outcome.error_code == "TASK_REFERENCE_AMBIGUOUS":
            return HarnessResult(
                status="awaiting_selection",
                command_id=command.command_id,
                command_type=command.type,
                effect={
                    "kind": "task_completion_ambiguous",
                    "query": outcome.query,
                    "filters": {"status": "active"},
                    "items": [
                        candidate.model_dump(mode="json")
                        for candidate in outcome.candidates
                    ],
                    "total": len(outcome.candidates),
                },
            )
        if outcome.error_code is not None:
            return HarnessResult(
                status="failed",
                command_id=command.command_id,
                command_type=command.type,
                error_code=outcome.error_code,
                effect={
                    "kind": "task_completion_not_found",
                    "query": outcome.query,
                    "filters": {"status": "active"},
                    "items": [],
                    "total": 0,
                },
            )
        if outcome.task is None:
            raise RuntimeError("successful task completion has no task result")
        return HarnessResult(
            status="duplicate" if outcome.duplicate else "executed",
            command_id=command.command_id,
            command_type=command.type,
            effect={
                "kind": "task_completed",
                "task_id": str(outcome.task.id),
                "title": outcome.task.title,
                "resolution": {"query": outcome.query, "candidate_count": 1},
            },
        )

    async def complete_task_by_id(command: Command, context: ExecutionContext) -> HarnessResult:
        """Conclui o candidato cujo ID já foi resolvido pelo Harness.

        Este caminho é usado depois que existe um único candidato, inclusive
        quando o usuário escolhe uma opção após ``TASK_REFERENCE_AMBIGUOUS``.
        O ID não é inventado pelo LLM nem recebido diretamente do usuário.
        """
        if not isinstance(command, TasksCompleteByIdCommand):
            raise TypeError("tasks.complete_by_id handler received an incompatible command")

        outcome = await task_service.complete_task_by_id(context, command.payload.task_id)
        if outcome.error_code is not None:
            return HarnessResult(
                status="failed",
                command_id=command.command_id,
                command_type=command.type,
                error_code=outcome.error_code,
            )
        if outcome.task is None:
            raise RuntimeError("successful task completion has no task result")
        return HarnessResult(
            status="duplicate" if outcome.duplicate else "executed",
            command_id=command.command_id,
            command_type=command.type,
            effect={
                "kind": "task_completed",
                "task_id": str(outcome.task.id),
                "title": outcome.task.title,
            },
        )

    handler: Callable[[Command, ExecutionContext], Awaitable[HarnessResult]] = create_task
    registry.register("tasks.create", handler)
    list_handler: Callable[[Command, ExecutionContext], Awaitable[HarnessResult]] = list_tasks
    registry.register("tasks.list", list_handler)
    complete_handler: Callable[[Command, ExecutionContext], Awaitable[HarnessResult]] = (
        complete_task_by_query
    )
    registry.register("tasks.complete", complete_handler)
    complete_by_id_handler: Callable[[Command, ExecutionContext], Awaitable[HarnessResult]] = (
        complete_task_by_id
    )
    registry.register("tasks.complete_by_id", complete_by_id_handler)
