"""Implementação SQLAlchemy do TaskRepository."""

import unicodedata
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.repositories.interfaces import TaskRepository
from app.schemas.commands import (
    TASK_UPDATE_FIELDS,
    TaskCreatePayload,
    TaskListPayload,
    TaskSearchPayload,
    TaskUpdateChanges,
)
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

    async def complete_for_user(self, user_id: UUID, task_id: UUID) -> TaskView | None:
        task = await self._session.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.user_id == user_id,
                Task.status == "active",
            ),
        )
        if task is None:
            return None
        task.status = "completed"
        task.completed_at = datetime.now(UTC)
        await self._session.flush()
        return TaskView.model_validate(task)

    async def update_for_user(
        self,
        user_id: UUID,
        task_id: UUID,
        payload: TaskUpdateChanges,
    ) -> TaskView | None:
        task = await self._session.scalar(
            select(Task).where(Task.id == task_id, Task.user_id == user_id),
        )
        if task is None:
            return None

        update_values = {
            field: getattr(payload, field)
            for field in TASK_UPDATE_FIELDS
            if field in payload.model_fields_set
        }

        for field in TASK_UPDATE_FIELDS:
            if field in update_values:
                setattr(task, field, update_values[field])

        await self._session.flush()
        return TaskView.model_validate(task)

    async def search_for_user(
        self,
        user_id: UUID,
        payload: TaskSearchPayload,
    ) -> TaskListResult:
        statement = select(Task).where(Task.user_id == user_id, Task.status == "active")
        tasks = (await self._session.scalars(statement)).all()
        query = _normalize_search_text(payload.query)
        terms = query.split()

        matches = []
        for task in tasks:
            searchable = _normalize_search_text(
                " ".join(part for part in (task.title, task.description) if part),
            )
            if all(term in searchable for term in terms):
                title = _normalize_search_text(task.title)
                exact_title_rank = 0 if title == query else 1
                title_rank = 0 if all(term in title for term in terms) else 1
                matches.append((exact_title_rank, title_rank, task))

        matches.sort(
            key=lambda item: (
                item[0],
                item[1],
                -item[2].priority,
                item[2].due_date is None,
                item[2].due_date,
                item[2].created_at,
            ),
        )
        items = [TaskView.model_validate(item[2]) for item in matches]
        return TaskListResult(items=items, total=len(items))

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

    async def delete_for_user(self, user_id: UUID, task_id: UUID) -> TaskView | None:
        task = await self._session.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.user_id == user_id,
                Task.status == "active",
            ),
        )
        if task is None:
            return None

        deleted = TaskView.model_validate(task)
        await self._session.delete(task)
        await self._session.flush()
        return deleted


def _normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_accents = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(without_accents.split())
