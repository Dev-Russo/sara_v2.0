"""Casos de uso de tarefas; transações são controladas aqui."""

from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.command_execution import CommandExecution
from app.repositories.command_execution_repository import SqlAlchemyCommandExecutionRepository
from app.repositories.task_repository import SqlAlchemyTaskRepository
from app.repositories.user_repository import SqlAlchemyUserRepository
from app.schemas.commands import (
    TASK_UPDATE_FIELDS,
    TaskCreatePayload,
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
    TaskListResult,
    TaskUpdateResult,
)


def _same_task_value(current: object, requested: object) -> bool:
    if isinstance(current, datetime) and isinstance(requested, datetime):
        current = _as_utc(current)
        requested = _as_utc(requested)
    return current == requested


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class TaskService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        timezone: str = "America/Sao_Paulo",
    ) -> None:
        self._session_factory = session_factory
        self._timezone = ZoneInfo(timezone)

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
        return datetime.now(self._timezone).date()

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
