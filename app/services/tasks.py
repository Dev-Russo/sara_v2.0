"""Casos de uso de tarefas; transações são controladas aqui."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.command_execution import CommandExecution
from app.repositories.command_execution_repository import SqlAlchemyCommandExecutionRepository
from app.repositories.confirmation_repository import SqlAlchemyConfirmationRepository
from app.repositories.task_repository import SqlAlchemyTaskRepository
from app.repositories.user_repository import SqlAlchemyUserRepository
from app.schemas.commands import (
    TASK_UPDATE_FIELDS,
    TaskCreatePayload,
    TaskDeletePayload,
    TaskIdPayload,
    TaskListPayload,
    TaskSearchPayload,
    TaskUpdateByIdPayload,
    TaskUpdateChanges,
    TaskUpdatePayload,
)
from app.schemas.events import ExecutionContext
from app.schemas.tasks import (
    TaskCandidate,
    TaskCompletionResult,
    TaskCreationResult,
    TaskDeletionResult,
    TaskListResult,
    TaskUpdateResult,
)

CONFIRMATION_TTL = timedelta(minutes=10)


def _same_task_value(current: object, requested: object) -> bool:
    if isinstance(current, datetime) and isinstance(requested, datetime):
        current = _as_utc(current)
        requested = _as_utc(requested)
    return current == requested


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _delete_confirmation_summary(title: str) -> str:
    visible_title = title if len(title) <= 80 else f"{title[:77]}..."
    return f'Excluir a tarefa "{visible_title}"? Essa ação não poderá ser desfeita.'


class TaskService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        timezone: str = "America/Sao_Paulo",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._timezone = ZoneInfo(timezone)
        self._clock = clock or (lambda: datetime.now(UTC))

    async def create_task(
        self,
        context: ExecutionContext,
        payload: TaskCreatePayload,
    ) -> TaskCreationResult:
        async with self._session_factory() as session:
            async with session.begin():
                user_repository = SqlAlchemyUserRepository(session)
                task_repository = SqlAlchemyTaskRepository(session)
                execution_repository = SqlAlchemyCommandExecutionRepository(session)

                await user_repository.ensure_exists(context.user_id)
                existing = await execution_repository.get_by_idempotency_key(
                    context.idempotency_key,
                )
                if existing is not None:
                    return await self._duplicate_result(
                        existing,
                        task_repository,
                        context.user_id,
                    )

                execution = await execution_repository.create_received(
                    context,
                    command_type="tasks.create",
                    command_version=1,
                )
                normalized_payload = payload
                if normalized_payload.due_date is None:
                    normalized_payload = payload.model_copy(update={"due_date": self._today()})

                task = await task_repository.create(context.user_id, normalized_payload)
                effect = {
                    "kind": "task_created",
                    "task_id": str(task.id),
                    "title": task.title,
                    "priority": task.priority,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                }
                execution.status = "executed"
                execution.effect_payload = effect
                execution.result_summary = task.title
                execution.completed_at = datetime.now(UTC)

                return TaskCreationResult(task=task, duplicate=False)

    def _today(self) -> date:
        return self._now().astimezone(self._timezone).date()

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    async def list_tasks(
        self,
        context: ExecutionContext,
        payload: TaskListPayload,
    ) -> TaskListResult:
        async with self._session_factory() as session:
            async with session.begin():
                user_repository = SqlAlchemyUserRepository(session)
                task_repository = SqlAlchemyTaskRepository(session)

                await user_repository.ensure_exists(context.user_id)
                return await task_repository.list_for_user(context.user_id, payload)

    async def search_tasks(
        self,
        context: ExecutionContext,
        payload: TaskSearchPayload,
    ) -> TaskListResult:
        async with self._session_factory() as session:
            async with session.begin():
                user_repository = SqlAlchemyUserRepository(session)
                task_repository = SqlAlchemyTaskRepository(session)

                await user_repository.ensure_exists(context.user_id)
                active_payload = payload.model_copy(update={"status": "active"})
                return await task_repository.search_for_user(context.user_id, active_payload)

    async def request_task_deletion(
        self,
        context: ExecutionContext,
        payload: TaskDeletePayload,
        *,
        command_id: UUID,
    ) -> TaskDeletionResult:
        """Resolve uma referência e cria confirmação antes de qualquer exclusão."""

        async with self._session_factory() as session:
            async with session.begin():
                user_repository = SqlAlchemyUserRepository(session)
                task_repository = SqlAlchemyTaskRepository(session)
                execution_repository = SqlAlchemyCommandExecutionRepository(session)
                confirmation_repository = SqlAlchemyConfirmationRepository(session)

                await user_repository.ensure_exists(context.user_id)
                existing = await execution_repository.get_by_idempotency_key(
                    context.idempotency_key,
                )
                if existing is not None:
                    return await self._duplicate_deletion_result(
                        existing,
                        task_repository,
                        context.user_id,
                    )

                execution = await execution_repository.create_received(
                    context,
                    command_type="tasks.delete",
                    command_version=1,
                )
                matches = await task_repository.search_for_user(
                    context.user_id,
                    TaskSearchPayload(query=payload.query, status="active"),
                )
                candidates = [
                    TaskCandidate(id=item.id, title=item.title, due_date=item.due_date)
                    for item in matches.items
                ]
                if not candidates:
                    effect = {
                        "kind": "task_delete_not_found",
                        "error_code": "TASK_REFERENCE_NOT_FOUND",
                        "query": payload.query,
                        "filters": {"status": "active"},
                        "items": [],
                        "total": 0,
                    }
                    self._finish_execution(
                        execution,
                        status="failed",
                        effect=effect,
                        result_summary=payload.query,
                    )
                    return TaskDeletionResult(
                        command_type="tasks.delete",
                        error_code="TASK_REFERENCE_NOT_FOUND",
                        query=payload.query,
                        effect=effect,
                    )

                if len(candidates) > 1:
                    effect = {
                        "kind": "task_delete_ambiguous",
                        "query": payload.query,
                        "filters": {"status": "active"},
                        "items": [candidate.model_dump(mode="json") for candidate in candidates],
                        "total": len(candidates),
                    }
                    self._finish_execution(
                        execution,
                        status="awaiting_selection",
                        effect=effect,
                        result_summary=payload.query,
                    )
                    return TaskDeletionResult(
                        command_type="tasks.delete",
                        error_code="TASK_REFERENCE_AMBIGUOUS",
                        candidates=candidates,
                        query=payload.query,
                        effect=effect,
                    )

                return await self._request_task_deletion_by_id(
                    context=context,
                    command_id=command_id,
                    command_type="tasks.delete",
                    task_id=candidates[0].id,
                    task_repository=task_repository,
                    confirmation_repository=confirmation_repository,
                    execution=execution,
                    query=payload.query,
                )

    async def request_task_deletion_by_id(
        self,
        context: ExecutionContext,
        task_id: UUID,
        *,
        command_id: UUID,
    ) -> TaskDeletionResult:
        """Cria confirmação para um ID resolvido pelo Graph."""

        async with self._session_factory() as session:
            async with session.begin():
                user_repository = SqlAlchemyUserRepository(session)
                task_repository = SqlAlchemyTaskRepository(session)
                execution_repository = SqlAlchemyCommandExecutionRepository(session)
                confirmation_repository = SqlAlchemyConfirmationRepository(session)

                await user_repository.ensure_exists(context.user_id)
                existing = await execution_repository.get_by_idempotency_key(
                    context.idempotency_key,
                )
                if existing is not None:
                    return await self._duplicate_deletion_result(
                        existing,
                        task_repository,
                        context.user_id,
                    )

                execution = await execution_repository.create_received(
                    context,
                    command_type="tasks.delete_by_id",
                    command_version=1,
                )
                return await self._request_task_deletion_by_id(
                    context=context,
                    command_id=command_id,
                    command_type="tasks.delete_by_id",
                    task_id=task_id,
                    task_repository=task_repository,
                    confirmation_repository=confirmation_repository,
                    execution=execution,
                )

    async def resolve_task_deletion_confirmation(
        self,
        confirmation_id: UUID,
        context: ExecutionContext,
        decision: str,
    ) -> TaskDeletionResult:
        """Resolve uma pendência persistida e executa a exclusão atomicamente."""

        async with self._session_factory() as session:
            async with session.begin():
                user_repository = SqlAlchemyUserRepository(session)
                task_repository = SqlAlchemyTaskRepository(session)
                execution_repository = SqlAlchemyCommandExecutionRepository(session)
                confirmation_repository = SqlAlchemyConfirmationRepository(session)

                await user_repository.ensure_exists(context.user_id)
                request = await confirmation_repository.get_for_user(
                    context.user_id,
                    confirmation_id,
                )
                if request is None:
                    return TaskDeletionResult(
                        error_code="CONFIRMATION_NOT_FOUND",
                        effect={"kind": "confirmation_not_found"},
                    )

                execution = await execution_repository.get_by_id(request.execution_id)
                if execution is None:
                    return TaskDeletionResult(
                        error_code="CONFIRMATION_NOT_FOUND",
                        effect={"kind": "confirmation_not_found"},
                    )

                effect = execution.effect_payload or {}
                if request.status == "consumed" or execution.status == "executed":
                    return TaskDeletionResult(
                        command_id=request.command_id,
                        command_type=request.command_type,
                        duplicate=True,
                        effect=effect,
                    )
                if request.status == "cancelled":
                    return TaskDeletionResult(
                        command_id=request.command_id,
                        command_type=request.command_type,
                        error_code="CONFIRMATION_CANCELLED",
                        effect=effect,
                    )
                if request.status == "expired":
                    return TaskDeletionResult(
                        command_id=request.command_id,
                        command_type=request.command_type,
                        error_code="CONFIRMATION_EXPIRED",
                        effect=effect,
                    )
                if decision not in {"confirm", "cancel"}:
                    return TaskDeletionResult(
                        command_id=request.command_id,
                        command_type=request.command_type,
                        error_code="CONFIRMATION_INVALID_DECISION",
                        confirmation_id=confirmation_id,
                        effect=effect,
                    )

                now = self._now()
                if now >= _as_utc(request.expires_at):
                    expired = await confirmation_repository.transition_pending(
                        user_id=context.user_id,
                        confirmation_id=confirmation_id,
                        status="expired",
                        resolved_at=now,
                    )
                    if not expired:
                        await session.refresh(execution)
                        refreshed = await confirmation_repository.get_for_user(
                            context.user_id,
                            confirmation_id,
                        )
                        latest_effect = execution.effect_payload or effect
                        if refreshed is not None and refreshed.status == "consumed":
                            return TaskDeletionResult(
                                command_id=request.command_id,
                                command_type=request.command_type,
                                duplicate=True,
                                effect=latest_effect,
                            )
                        if refreshed is not None and refreshed.status == "cancelled":
                            return TaskDeletionResult(
                                command_id=request.command_id,
                                command_type=request.command_type,
                                error_code="CONFIRMATION_CANCELLED",
                                effect=latest_effect,
                            )
                        if refreshed is not None and refreshed.status == "expired":
                            return TaskDeletionResult(
                                command_id=request.command_id,
                                command_type=request.command_type,
                                error_code="CONFIRMATION_EXPIRED",
                                effect=latest_effect,
                            )
                        return TaskDeletionResult(
                            command_id=request.command_id,
                            command_type=request.command_type,
                            error_code="CONFIRMATION_ALREADY_RESOLVED",
                            effect=latest_effect,
                        )
                    failure_effect = {
                        "kind": "task_delete_failed",
                        "confirmation_id": str(confirmation_id),
                        "error_code": "CONFIRMATION_EXPIRED",
                    }
                    self._finish_execution(
                        execution,
                        status="failed",
                        effect=failure_effect,
                        result_summary=str(confirmation_id),
                    )
                    return TaskDeletionResult(
                        command_id=request.command_id,
                        command_type=request.command_type,
                        error_code="CONFIRMATION_EXPIRED",
                        effect=failure_effect,
                    )

                transitioned = await confirmation_repository.transition_pending(
                    user_id=context.user_id,
                    confirmation_id=confirmation_id,
                    status="confirmed" if decision == "confirm" else "cancelled",
                    resolved_at=now,
                )
                if not transitioned:
                    refreshed = await confirmation_repository.get_for_user(
                        context.user_id,
                        confirmation_id,
                    )
                    if refreshed is not None and refreshed.status == "consumed":
                        return TaskDeletionResult(
                            command_id=request.command_id,
                            command_type=request.command_type,
                            duplicate=True,
                            effect=effect,
                        )
                    return TaskDeletionResult(
                        command_id=request.command_id,
                        command_type=request.command_type,
                        error_code="CONFIRMATION_ALREADY_RESOLVED",
                        effect=effect,
                    )

                if decision == "cancel":
                    cancelled_effect = {
                        "kind": "task_delete_cancelled",
                        "confirmation_id": str(confirmation_id),
                    }
                    self._finish_execution(
                        execution,
                        status="rejected",
                        effect=cancelled_effect,
                        result_summary=str(confirmation_id),
                    )
                    return TaskDeletionResult(
                        command_id=request.command_id,
                        command_type=request.command_type,
                        error_code="CONFIRMATION_CANCELLED",
                        effect=cancelled_effect,
                    )

                payload = TaskIdPayload.model_validate(request.payload_snapshot)
                task = await task_repository.delete_for_user(context.user_id, payload.task_id)
                if task is None:
                    request.status = "consumed"
                    request.resolved_at = now
                    await session.flush()
                    failure_effect = {
                        "kind": "task_delete_failed",
                        "task_id": str(payload.task_id),
                        "error_code": "TASK_NOT_FOUND",
                    }
                    self._finish_execution(
                        execution,
                        status="failed",
                        effect=failure_effect,
                        result_summary=str(payload.task_id),
                    )
                    return TaskDeletionResult(
                        command_id=request.command_id,
                        command_type=request.command_type,
                        error_code="TASK_NOT_FOUND",
                        effect=failure_effect,
                    )

                executed_effect = {
                    "kind": "task_deleted",
                    "task_id": str(task.id),
                    "title": task.title,
                }
                self._finish_execution(
                    execution,
                    status="executed",
                    effect=executed_effect,
                    result_summary=task.title,
                )
                request.status = "consumed"
                request.resolved_at = now
                await session.flush()
                return TaskDeletionResult(
                    command_id=request.command_id,
                    command_type=request.command_type,
                    task=task,
                    effect=executed_effect,
                )

    async def _request_task_deletion_by_id(
        self,
        *,
        context: ExecutionContext,
        command_id: UUID,
        command_type: str,
        task_id: UUID,
        task_repository: SqlAlchemyTaskRepository,
        confirmation_repository: SqlAlchemyConfirmationRepository,
        execution: CommandExecution,
        query: str | None = None,
    ) -> TaskDeletionResult:
        task = await task_repository.get_for_user(context.user_id, task_id)
        if task is None or task.status != "active":
            effect = {
                "kind": "task_delete_failed",
                "task_id": str(task_id),
                "error_code": "TASK_NOT_FOUND",
            }
            self._finish_execution(
                execution,
                status="failed",
                effect=effect,
                result_summary=str(task_id),
            )
            return TaskDeletionResult(
                command_type=command_type,
                error_code="TASK_NOT_FOUND",
                query=query,
                effect=effect,
            )

        expires_at = self._now() + CONFIRMATION_TTL
        confirmation = await confirmation_repository.create_pending(
            user_id=context.user_id,
            execution_id=execution.id,
            command_id=command_id,
            command_type=command_type,
            payload_snapshot={"task_id": str(task.id)},
            summary=_delete_confirmation_summary(task.title),
            expires_at=expires_at,
        )
        effect = {
            "kind": "task_delete_pending",
            "task_id": str(task.id),
            "title": task.title,
            "confirmation_id": str(confirmation.id),
            "summary": confirmation.summary,
            "expires_at": expires_at.isoformat(),
            "irreversible": True,
        }
        self._finish_execution(
            execution,
            status="awaiting_confirmation",
            effect=effect,
            result_summary=task.title,
        )
        return TaskDeletionResult(
            command_type=command_type,
            task=task,
            awaiting_confirmation=True,
            confirmation_id=confirmation.id,
            query=query,
            effect=effect,
        )

    async def _duplicate_deletion_result(
        self,
        execution: CommandExecution,
        task_repository: SqlAlchemyTaskRepository,
        user_id: UUID,
    ) -> TaskDeletionResult:
        effect = execution.effect_payload or {}
        if execution.status == "awaiting_selection":
            candidates = [
                TaskCandidate.model_validate(item)
                for item in effect.get("items", [])
                if isinstance(item, dict)
            ]
            return TaskDeletionResult(
                command_type=execution.command_type,
                candidates=candidates,
                query=effect.get("query") if isinstance(effect.get("query"), str) else None,
                effect=effect,
            )
        if execution.status == "awaiting_confirmation":
            confirmation_id = effect.get("confirmation_id")
            return TaskDeletionResult(
                command_type=execution.command_type,
                awaiting_confirmation=True,
                confirmation_id=UUID(str(confirmation_id)) if confirmation_id else None,
                query=effect.get("query") if isinstance(effect.get("query"), str) else None,
                effect=effect,
                duplicate=True,
            )
        if execution.status == "failed":
            return TaskDeletionResult(
                command_type=execution.command_type,
                error_code=str(effect.get("error_code", "TASK_NOT_FOUND")),
                query=effect.get("query") if isinstance(effect.get("query"), str) else None,
                effect=effect,
            )
        if execution.status == "rejected":
            return TaskDeletionResult(
                command_type=execution.command_type,
                error_code="CONFIRMATION_CANCELLED",
                effect=effect,
            )
        if execution.status != "executed":
            raise RuntimeError("idempotent task deletion is not in a completed state")

        task_id = effect.get("task_id")
        task = await task_repository.get_for_user(user_id, UUID(str(task_id))) if task_id else None
        return TaskDeletionResult(
            command_type=execution.command_type,
            task=task,
            duplicate=True,
            effect=effect,
        )

    @staticmethod
    def _finish_execution(
        execution: CommandExecution,
        *,
        status: str,
        effect: dict[str, object],
        result_summary: str,
    ) -> None:
        execution.status = status
        execution.effect_payload = effect
        execution.result_summary = result_summary
        execution.completed_at = (
            None
            if status in {"awaiting_confirmation", "awaiting_selection"}
            else datetime.now(UTC)
        )

    async def update_task(
        self,
        context: ExecutionContext,
        payload: TaskUpdatePayload,
    ) -> TaskUpdateResult:
        async with self._session_factory() as session:
            async with session.begin():
                user_repository = SqlAlchemyUserRepository(session)
                task_repository = SqlAlchemyTaskRepository(session)
                execution_repository = SqlAlchemyCommandExecutionRepository(session)

                await user_repository.ensure_exists(context.user_id)
                existing = await execution_repository.get_by_idempotency_key(
                    context.idempotency_key,
                )
                if existing is not None:
                    # Reentregas devem reutilizar o efeito persistido e nunca repetir a mutação.
                    return await self._duplicate_update_result(
                        existing,
                        task_repository,
                        context.user_id,
                    )

                execution = await execution_repository.create_received(
                    context,
                    command_type="tasks.update",
                    command_version=1,
                )
                matches = await task_repository.search_for_user(
                    context.user_id,
                    TaskSearchPayload(query=payload.query, status="active"),
                )
                candidates = [
                    TaskCandidate(id=item.id, title=item.title, due_date=item.due_date)
                    for item in matches.items
                ]
                if not candidates:
                    effect = {
                        "kind": "task_update_not_found",
                        "query": payload.query,
                        "filters": {"status": "active"},
                        "items": [],
                        "total": 0,
                    }
                    execution.status = "failed"
                    execution.effect_payload = effect
                    execution.result_summary = payload.query
                    execution.completed_at = datetime.now(UTC)
                    return TaskUpdateResult(
                        error_code="TASK_REFERENCE_NOT_FOUND",
                        query=payload.query,
                        effect=effect,
                    )

                if len(candidates) > 1:
                    effect = {
                        "kind": "task_update_ambiguous",
                        "query": payload.query,
                        "filters": {"status": "active"},
                        "items": [candidate.model_dump(mode="json") for candidate in candidates],
                        "total": len(candidates),
                    }
                    execution.status = "awaiting_selection"
                    execution.effect_payload = effect
                    execution.result_summary = payload.query
                    return TaskUpdateResult(
                        error_code="TASK_REFERENCE_AMBIGUOUS",
                        candidates=candidates,
                        query=payload.query,
                        effect=effect,
                    )
                return await self._apply_task_update(
                    context=context,
                    task_repository=task_repository,
                    execution=execution,
                    task_id=candidates[0].id,
                    changes=payload,
                    query=payload.query,
                )

    async def update_task_by_id(
        self,
        context: ExecutionContext,
        payload: TaskUpdateByIdPayload,
    ) -> TaskUpdateResult:
        """Atualiza diretamente uma tarefa cujo ID já foi resolvido pelo Harness."""
        async with self._session_factory() as session:
            async with session.begin():
                user_repository = SqlAlchemyUserRepository(session)
                task_repository = SqlAlchemyTaskRepository(session)
                execution_repository = SqlAlchemyCommandExecutionRepository(session)

                await user_repository.ensure_exists(context.user_id)
                existing = await execution_repository.get_by_idempotency_key(
                    context.idempotency_key,
                )
                if existing is not None:
                    return await self._duplicate_update_result(
                        existing,
                        task_repository,
                        context.user_id,
                    )

                execution = await execution_repository.create_received(
                    context,
                    command_type="tasks.update_by_id",
                    command_version=1,
                )
                return await self._apply_task_update(
                    context=context,
                    task_repository=task_repository,
                    execution=execution,
                    task_id=payload.task_id,
                    changes=payload,
                )

    async def _apply_task_update(
        self,
        *,
        context: ExecutionContext,
        task_repository: SqlAlchemyTaskRepository,
        execution: CommandExecution,
        task_id: UUID,
        changes: TaskUpdateChanges,
        query: str | None = None,
    ) -> TaskUpdateResult:
        """Aplica a mutação comum depois que o ID já foi resolvido."""
        existing_task = await task_repository.get_for_user(context.user_id, task_id)
        if existing_task is None:
            effect = {
                "kind": "task_update_failed",
                "task_id": str(task_id),
                "error_code": "TASK_NOT_FOUND",
            }
            execution.status = "failed"
            execution.effect_payload = effect
            execution.result_summary = str(task_id)
            execution.completed_at = datetime.now(UTC)
            return TaskUpdateResult(error_code="TASK_NOT_FOUND", effect=effect, query=query)

        changed_fields = [
            field
            for field in TASK_UPDATE_FIELDS
            if field in changes.model_fields_set
            and not _same_task_value(
                getattr(existing_task, field),
                getattr(changes, field),
            )
        ]
        task = (
            await task_repository.update_for_user(context.user_id, task_id, changes)
            if changed_fields
            else existing_task
        )
        if task is None:
            effect = {
                "kind": "task_update_failed",
                "task_id": str(task_id),
                "error_code": "TASK_NOT_FOUND",
            }
            execution.status = "failed"
            execution.effect_payload = effect
            execution.result_summary = str(task_id)
            execution.completed_at = datetime.now(UTC)
            return TaskUpdateResult(error_code="TASK_NOT_FOUND", effect=effect, query=query)

        effect: dict[str, object] = {
            "kind": "task_updated" if changed_fields else "task_unchanged",
            "task_id": str(task.id),
            "title": task.title,
            "changed_fields": changed_fields,
        }
        if query is not None:
            effect["resolution"] = {"query": query, "candidate_count": 1}
        execution.status = "executed"
        execution.effect_payload = effect
        execution.result_summary = task.title
        execution.completed_at = datetime.now(UTC)
        return TaskUpdateResult(
            task=task,
            changed_fields=changed_fields,
            query=query,
            effect=effect,
        )

    async def complete_task_by_query(
        self,
        context: ExecutionContext,
        query: str | None,
    ) -> TaskCompletionResult:
        """Busca tarefas pendentes e resolve uma conclusão por descrição.

        É a primeira etapa do fluxo de conclusão: pode retornar nenhum
        candidato, um candidato para conclusão imediata ou vários candidatos
        para ``TASK_REFERENCE_AMBIGUOUS`` e escolha posterior.
        """
        async with self._session_factory() as session:
            async with session.begin():
                user_repository = SqlAlchemyUserRepository(session)
                task_repository = SqlAlchemyTaskRepository(session)
                execution_repository = SqlAlchemyCommandExecutionRepository(session)

                await user_repository.ensure_exists(context.user_id)
                existing = await execution_repository.get_by_idempotency_key(
                    context.idempotency_key,
                )
                if existing is not None:
                    return await self._duplicate_completion_result(
                        existing,
                        task_repository,
                        context.user_id,
                    )

                execution = await execution_repository.create_received(
                    context,
                    command_type="tasks.complete",
                    command_version=1,
                )
                if query is None:
                    matches = await task_repository.list_for_user(
                        context.user_id,
                        TaskListPayload(status="active"),
                    )
                else:
                    matches = await task_repository.search_for_user(
                        context.user_id,
                        TaskSearchPayload(query=query, status="active"),
                    )

                candidates = [
                    TaskCandidate(id=item.id, title=item.title, due_date=item.due_date)
                    for item in matches.items
                ]
                if not candidates:
                    effect = {
                        "kind": "task_completion_not_found",
                        "query": query,
                        "filters": {"status": "active"},
                        "items": [],
                        "total": 0,
                    }
                    execution.status = "failed"
                    execution.effect_payload = effect
                    execution.result_summary = query or "task completion without reference"
                    execution.completed_at = datetime.now(UTC)
                    return TaskCompletionResult(
                        error_code="TASK_REFERENCE_NOT_FOUND",
                        query=query,
                    )

                if len(candidates) > 1:
                    effect = {
                        "kind": "task_completion_ambiguous",
                        "query": query,
                        "filters": {"status": "active"},
                        "items": [candidate.model_dump(mode="json") for candidate in candidates],
                        "total": len(candidates),
                    }
                    execution.status = "awaiting_selection"
                    execution.effect_payload = effect
                    execution.result_summary = query or "multiple active tasks"
                    return TaskCompletionResult(
                        error_code="TASK_REFERENCE_AMBIGUOUS",
                        candidates=candidates,
                        query=query,
                    )

                return await self._apply_task_completion(
                    context=context,
                    task_repository=task_repository,
                    execution=execution,
                    task_id=candidates[0].id,
                    query=query,
                )

    async def complete_task_by_id(
        self,
        context: ExecutionContext,
        task_id: UUID,
    ) -> TaskCompletionResult:
        """Conclui diretamente uma tarefa com ID já resolvido.

        O Graph/Harness usa este caminho somente depois de obter um único
        candidato, inclusive após a seleção explícita do usuário.
        """
        async with self._session_factory() as session:
            async with session.begin():
                user_repository = SqlAlchemyUserRepository(session)
                task_repository = SqlAlchemyTaskRepository(session)
                execution_repository = SqlAlchemyCommandExecutionRepository(session)

                await user_repository.ensure_exists(context.user_id)
                existing = await execution_repository.get_by_idempotency_key(
                    context.idempotency_key,
                )
                if existing is not None:
                    return await self._duplicate_completion_result(
                        existing,
                        task_repository,
                        context.user_id,
                    )

                execution = await execution_repository.create_received(
                    context,
                    command_type="tasks.complete_by_id",
                    command_version=1,
                )
                return await self._apply_task_completion(
                    context=context,
                    task_repository=task_repository,
                    execution=execution,
                    task_id=task_id,
                )

    async def _apply_task_completion(
        self,
        *,
        context: ExecutionContext,
        task_repository: SqlAlchemyTaskRepository,
        execution: CommandExecution,
        task_id: UUID,
        query: str | None = None,
    ) -> TaskCompletionResult:
        """Aplica a mutação comum depois que o ID já foi resolvido."""

        task = await task_repository.complete_for_user(context.user_id, task_id)
        if task is None:
            execution.status = "failed"
            execution.effect_payload = {
                "kind": "task_completion_failed",
                "task_id": str(task_id),
                "error_code": "TASK_NOT_FOUND",
            }
            execution.result_summary = str(task_id)
            execution.completed_at = datetime.now(UTC)
            return TaskCompletionResult(error_code="TASK_NOT_FOUND", query=query)

        effect: dict[str, object] = {
            "kind": "task_completed",
            "task_id": str(task.id),
            "title": task.title,
        }
        if query is not None:
            effect["resolution"] = {"query": query, "candidate_count": 1}
        execution.status = "executed"
        execution.effect_payload = effect
        execution.result_summary = task.title
        execution.completed_at = datetime.now(UTC)
        return TaskCompletionResult(task=task, query=query)

    async def _duplicate_result(
        self,
        execution: CommandExecution,
        task_repository: SqlAlchemyTaskRepository,
        user_id: UUID,
    ) -> TaskCreationResult:
        if execution.status != "executed" or not execution.effect_payload:
            raise RuntimeError("idempotent command is not in a completed state")

        task_id = UUID(str(execution.effect_payload["task_id"]))
        task = await task_repository.get_for_user(user_id, task_id)
        if task is None:
            raise RuntimeError("idempotent task result is no longer available")
        return TaskCreationResult(task=task, duplicate=True)

    async def _duplicate_update_result(
        self,
        execution: CommandExecution,
        task_repository: SqlAlchemyTaskRepository,
        user_id: UUID,
    ) -> TaskUpdateResult:
        effect = execution.effect_payload or {}
        if execution.status == "failed":
            return TaskUpdateResult(
                error_code=str(effect.get("error_code", "TASK_NOT_FOUND")),
                query=effect.get("query") if isinstance(effect.get("query"), str) else None,
                effect=effect,
            )
        if execution.status == "awaiting_selection":
            candidates = [
                TaskCandidate.model_validate(item)
                for item in effect.get("items", [])
                if isinstance(item, dict)
            ]
            return TaskUpdateResult(
                error_code="TASK_REFERENCE_AMBIGUOUS",
                candidates=candidates,
                query=effect.get("query") if isinstance(effect.get("query"), str) else None,
                effect=effect,
            )
        if execution.status != "executed" or not execution.effect_payload:
            raise RuntimeError("idempotent task update is not in a completed state")

        task_id = UUID(str(execution.effect_payload["task_id"]))
        task = await task_repository.get_for_user(user_id, task_id)
        if task is None:
            raise RuntimeError("idempotent task update result is no longer available")
        raw_changed_fields = effect.get("changed_fields", [])
        changed_fields = (
            [field for field in raw_changed_fields if isinstance(field, str)]
            if isinstance(raw_changed_fields, list)
            else []
        )
        return TaskUpdateResult(
            task=task,
            changed_fields=changed_fields,
            duplicate=True,
            query=effect.get("resolution", {}).get("query")
            if isinstance(effect.get("resolution"), dict)
            else None,
            effect=effect,
        )

    async def _duplicate_completion_result(
        self,
        execution: CommandExecution,
        task_repository: SqlAlchemyTaskRepository,
        user_id: UUID,
    ) -> TaskCompletionResult:
        effect = execution.effect_payload or {}
        if execution.status == "failed":
            return TaskCompletionResult(
                error_code=str(effect.get("error_code", "TASK_NOT_FOUND")),
                query=effect.get("query") if isinstance(effect.get("query"), str) else None,
            )
        if execution.status == "awaiting_selection":
            candidates = [
                TaskCandidate.model_validate(item)
                for item in effect.get("items", [])
                if isinstance(item, dict)
            ]
            return TaskCompletionResult(
                error_code="TASK_REFERENCE_AMBIGUOUS",
                candidates=candidates,
                query=effect.get("query") if isinstance(effect.get("query"), str) else None,
            )
        if execution.status != "executed" or not execution.effect_payload:
            raise RuntimeError("idempotent completion is not in a completed state")

        task_id = UUID(str(execution.effect_payload["task_id"]))
        task = await task_repository.get_for_user(user_id, task_id)
        if task is None:
            raise RuntimeError("idempotent task result is no longer available")
        return TaskCompletionResult(
            task=task,
            duplicate=True,
            query=effect.get("resolution", {}).get("query")
            if isinstance(effect.get("resolution"), dict)
            else None,
        )
