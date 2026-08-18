"""Implementação SQLAlchemy do TaskRepository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.repositories.interfaces import TaskRepository
from app.schemas.commands import TaskCreatePayload, TaskListPayload
from app.schemas.tasks import TaskListResult, TaskView


class SqlAlchemyTaskRepository(TaskRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: UUID, payload: TaskCreatePayload) -> TaskView:
        task = Task(
            user_id=user_id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            due_date=payload.due_date,
            start_at=payload.start_at,
            end_at=payload.end_at,
        )
        self._session.add(task)
        await self._session.flush()
        return TaskView.model_validate(task)

    async def get_for_user(self, user_id: UUID, task_id: UUID) -> TaskView | None:
        task = await self._session.scalar(
            select(Task).where(Task.id == task_id, Task.user_id == user_id),
        )
        return TaskView.model_validate(task) if task else None

    async def list_for_user(
        self,
        user_id: UUID,
        payload: TaskListPayload,
    ) -> TaskListResult:
        statement = select(Task).where(Task.user_id == user_id)
        if payload.status is not None:
            statement = statement.where(Task.status == payload.status)
        if payload.due_date_from is not None:
            statement = statement.where(Task.due_date >= payload.due_date_from)
        if payload.due_date_to is not None:
            statement = statement.where(Task.due_date <= payload.due_date_to)

        statement = statement.order_by(
            Task.priority.desc(),
            Task.due_date.asc().nulls_last(),
            Task.created_at.desc(),
        )
        tasks = (await self._session.scalars(statement)).all()
        items = [TaskView.model_validate(task) for task in tasks]
        return TaskListResult(items=items, total=len(items))
