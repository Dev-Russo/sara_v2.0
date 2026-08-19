from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.harness.handlers import register_task_handlers
from app.harness.registry import CommandRegistry
from app.harness.service import Harness
from app.schemas.commands import TaskCreatePayload, TasksCompleteCommand
from app.schemas.events import ExecutionContext
from app.services.tasks import TaskService


def make_context(*, user_id: UUID, idempotency_key: str) -> ExecutionContext:
    return ExecutionContext(
        user_id=user_id,
        graph_thread_id="task-completion-thread",
        correlation_id=idempotency_key,
        idempotency_key=idempotency_key,
        source="test",
    )


@pytest.mark.asyncio
async def test_task_service_completes_task_by_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    created = await service.create_task(
        make_context(user_id=user_id, idempotency_key="completion-create"),
        TaskCreatePayload(title="Ir à academia"),
    )

    result = await service.complete_task_by_id(
        make_context(user_id=user_id, idempotency_key="completion-complete"),
        created.task.id,
    )

    assert result.task.id == created.task.id
    assert result.task.status == "completed"
    assert result.task.completed_at is not None
    assert result.task.completed_at <= datetime.now(UTC)


@pytest.mark.asyncio
async def test_harness_searches_and_executes_tasks_complete(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    harness = Harness(registry)
    user_id = uuid4()
    created = await service.create_task(
        make_context(user_id=user_id, idempotency_key="harness-completion-create"),
        TaskCreatePayload(title="Ler documentação"),
    )

    result = await harness.handle(
        TasksCompleteCommand(
            type="tasks.complete",
            payload={"query": "Ler documentação"},
        ),
        make_context(user_id=user_id, idempotency_key="harness-completion-command"),
    )

    assert result.status == "executed"
    assert result.command_type == "tasks.complete"
    assert result.effect == {
        "kind": "task_completed",
        "task_id": str(created.task.id),
        "title": "Ler documentação",
        "resolution": {"query": "Ler documentação", "candidate_count": 1},
    }
