from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.harness.handlers import register_task_handlers
from app.harness.registry import CommandRegistry
from app.harness.service import Harness
from app.schemas.commands import TaskCreatePayload, TasksCreateCommand
from app.schemas.events import ExecutionContext
from app.services.tasks import TaskService


def make_context(*, idempotency_key: str) -> ExecutionContext:
    return ExecutionContext(
        user_id=uuid4(),
        graph_thread_id="test-thread",
        correlation_id="test-correlation",
        idempotency_key=idempotency_key,
        source="test",
    )


@pytest.mark.asyncio
async def test_create_task_returns_persisted_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    context = make_context(idempotency_key="create-task-1")

    result = await service.create_task(
        context,
        TaskCreatePayload(title="Estudar arquitetura", priority=1),
    )

    assert result.duplicate is False
    assert result.task.title == "Estudar arquitetura"
    assert result.task.priority == 1
    assert result.task.status == "active"
    assert result.task.user_id == context.user_id


@pytest.mark.asyncio
async def test_create_task_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    context = make_context(idempotency_key="create-task-duplicate")
    payload = TaskCreatePayload(title="Não duplicar")

    first = await service.create_task(context, payload)
    second = await service.create_task(context, payload)

    assert first.task.id == second.task.id
    assert second.duplicate is True


@pytest.mark.asyncio
async def test_harness_executes_tasks_create(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    harness = Harness(registry)
    context = make_context(idempotency_key="harness-create-1")
    command = TasksCreateCommand(
        type="tasks.create",
        payload={"title": "Criar pelo Harness", "priority": 1},
    )

    result = await harness.handle(command, context)

    assert result.status == "executed"
    assert result.command_type == "tasks.create"
    assert result.effect is not None
    assert result.effect["kind"] == "task_created"
    assert result.effect["title"] == "Criar pelo Harness"
    assert result.effect["priority"] == 1
    assert result.effect["task_id"]
