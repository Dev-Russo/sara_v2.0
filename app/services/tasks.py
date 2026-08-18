"""Casos de uso de tarefas; transações são controladas aqui."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.command_execution import CommandExecution
from app.repositories.command_execution_repository import SqlAlchemyCommandExecutionRepository
from app.repositories.task_repository import SqlAlchemyTaskRepository
from app.repositories.user_repository import SqlAlchemyUserRepository
from app.schemas.commands import TaskCreatePayload, TaskListPayload
from app.schemas.events import ExecutionContext
from app.schemas.tasks import TaskCreationResult, TaskListResult


class TaskService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

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
                task = await task_repository.create(context.user_id, payload)
                effect = {
                    "kind": "task_created",
                    "task_id": str(task.id),
                    "title": task.title,
                    "priority": task.priority,
                }
                execution.status = "executed"
                execution.effect_payload = effect
                execution.result_summary = task.title
                execution.completed_at = datetime.now(UTC)

                return TaskCreationResult(task=task, duplicate=False)

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
