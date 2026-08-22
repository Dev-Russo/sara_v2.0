"""Handlers que adaptam casos de uso para o contrato do Harness."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from app.harness.registry import CommandRegistry
from app.harness.service import ConfirmationResolver
from app.schemas.commands import (
    Command,
    TasksCompleteByIdCommand,
    TasksCompleteCommand,
    TasksCreateCommand,
    TasksDeleteByIdCommand,
    TasksDeleteCommand,
    TasksListCommand,
    TasksUpdateByIdCommand,
    TasksUpdateCommand,
)
from app.schemas.events import ExecutionContext
from app.schemas.results import HarnessResult
from app.schemas.tasks import TaskDeletionResult
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

    async def delete_task_by_query(command: Command, context: ExecutionContext) -> HarnessResult:
        if not isinstance(command, TasksDeleteCommand):
            raise TypeError("tasks.delete handler received an incompatible command")

        outcome = await task_service.request_task_deletion(
            context,
            command.payload,
            command_id=command.command_id,
        )
        return _task_deletion_result(command.command_id, command.type, outcome)

    async def delete_task_by_id(command: Command, context: ExecutionContext) -> HarnessResult:
        if not isinstance(command, TasksDeleteByIdCommand):
            raise TypeError("tasks.delete_by_id handler received an incompatible command")

        outcome = await task_service.request_task_deletion_by_id(
            context,
            command.payload.task_id,
            command_id=command.command_id,
        )
        return _task_deletion_result(command.command_id, command.type, outcome)

    async def update_task_by_query(command: Command, context: ExecutionContext) -> HarnessResult:
        if not isinstance(command, TasksUpdateCommand):
            raise TypeError("tasks.update handler received an incompatible command")

        outcome = await task_service.update_task(context, command.payload)
        if outcome.error_code == "TASK_REFERENCE_AMBIGUOUS":
            return HarnessResult(
                status="awaiting_selection",
                command_id=command.command_id,
                command_type=command.type,
                effect=outcome.effect,
            )
        if outcome.error_code is not None:
            return HarnessResult(
                status="failed",
                command_id=command.command_id,
                command_type=command.type,
                error_code=outcome.error_code,
                effect=outcome.effect,
            )
        if outcome.task is None:
            raise RuntimeError("successful task update has no task result")
        return HarnessResult(
            status="duplicate" if outcome.duplicate else "executed",
            command_id=command.command_id,
            command_type=command.type,
            effect=outcome.effect,
        )

    async def update_task_by_id(command: Command, context: ExecutionContext) -> HarnessResult:
        if not isinstance(command, TasksUpdateByIdCommand):
            raise TypeError("tasks.update_by_id handler received an incompatible command")

        outcome = await task_service.update_task_by_id(context, command.payload)
        if outcome.error_code is not None:
            return HarnessResult(
                status="failed",
                command_id=command.command_id,
                command_type=command.type,
                error_code=outcome.error_code,
                effect=outcome.effect,
            )
        if outcome.task is None:
            raise RuntimeError("successful task update has no task result")
        return HarnessResult(
            status="duplicate" if outcome.duplicate else "executed",
            command_id=command.command_id,
            command_type=command.type,
            effect=outcome.effect,
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
    delete_handler: Callable[[Command, ExecutionContext], Awaitable[HarnessResult]] = (
        delete_task_by_query
    )
    registry.register("tasks.delete", delete_handler)
    delete_by_id_handler: Callable[[Command, ExecutionContext], Awaitable[HarnessResult]] = (
        delete_task_by_id
    )
    registry.register("tasks.delete_by_id", delete_by_id_handler)
    update_handler: Callable[[Command, ExecutionContext], Awaitable[HarnessResult]] = (
        update_task_by_query
    )
    registry.register("tasks.update", update_handler)
    update_by_id_handler: Callable[[Command, ExecutionContext], Awaitable[HarnessResult]] = (
        update_task_by_id
    )
    registry.register("tasks.update_by_id", update_by_id_handler)
    complete_handler: Callable[[Command, ExecutionContext], Awaitable[HarnessResult]] = (
        complete_task_by_query
    )
    registry.register("tasks.complete", complete_handler)
    complete_by_id_handler: Callable[[Command, ExecutionContext], Awaitable[HarnessResult]] = (
        complete_task_by_id
    )
    registry.register("tasks.complete_by_id", complete_by_id_handler)


class TaskConfirmationResolver:
    """Adapta a resolução do caso de uso para a seam do Harness."""

    def __init__(self, task_service: TaskService) -> None:
        self._task_service = task_service

    async def resolve(
        self,
        confirmation_id: UUID,
        context: ExecutionContext,
        decision: str,
    ) -> HarnessResult:
        outcome = await self._task_service.resolve_task_deletion_confirmation(
            confirmation_id,
            context,
            decision,
        )
        return _task_deletion_result(
            outcome.command_id or confirmation_id,
            outcome.command_type or "tasks.delete",
            outcome,
        )


def build_task_confirmation_resolver(task_service: TaskService) -> ConfirmationResolver:
    return TaskConfirmationResolver(task_service)


def _task_deletion_result(
    command_id: UUID,
    command_type: str,
    outcome: TaskDeletionResult,
) -> HarnessResult:
    effect = outcome.effect
    if effect is not None and effect.get("kind") == "task_delete_ambiguous":
        return HarnessResult(
            status="awaiting_selection",
            command_id=command_id,
            command_type=command_type,
            effect=effect,
        )
    if outcome.awaiting_confirmation:
        return HarnessResult(
            status="awaiting_confirmation",
            command_id=command_id,
            command_type=command_type,
            confirmation_id=outcome.confirmation_id,
            effect=effect,
        )
    if outcome.error_code is not None:
        status = "rejected" if outcome.error_code == "CONFIRMATION_CANCELLED" else "failed"
        return HarnessResult(
            status=status,
            command_id=command_id,
            command_type=command_type,
            error_code=outcome.error_code,
            effect=effect,
        )
    if effect is None:
        raise RuntimeError("successful task deletion has no effect")
    return HarnessResult(
        status="duplicate" if outcome.duplicate else "executed",
        command_id=command_id,
        command_type=command_type,
        effect=effect,
    )
