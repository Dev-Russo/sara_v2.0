from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.schemas.commands import TaskCreatePayload, TaskSearchPayload
from app.schemas.events import ExecutionContext
from app.services.tasks import TaskService


def make_context(*, user_id: UUID, idempotency_key: str) -> ExecutionContext:
    return ExecutionContext(
        user_id=user_id,
        graph_thread_id="task-search-thread",
        correlation_id=idempotency_key,
        idempotency_key=idempotency_key,
        source="test",
    )


@pytest.mark.asyncio
async def test_task_search_returns_only_active_text_matches(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    active = await service.create_task(
        make_context(user_id=user_id, idempotency_key="search-active"),
        TaskCreatePayload(title="Ir à academia"),
    )
    completed = await service.create_task(
        make_context(user_id=user_id, idempotency_key="search-completed-create"),
        TaskCreatePayload(title="Voltar à academia"),
    )
    await service.complete_task(
        make_context(user_id=user_id, idempotency_key="search-completed"),
        completed.task.id,
    )

    result = await service.search_tasks(
        make_context(user_id=user_id, idempotency_key="search-query"),
        TaskSearchPayload(query="ACADEMIA", status="completed"),
    )

    assert result.total == 1
    assert result.items[0].id == active.task.id
    assert result.items[0].title == "Ir à academia"
