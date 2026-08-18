from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.task import TaskAgent
from app.graph.builder import build_graph
from app.harness.handlers import register_task_handlers
from app.harness.registry import CommandRegistry
from app.harness.service import Harness
from app.models.task import Task
from app.schemas.commands import TaskCreatePayload, TaskListPayload
from app.schemas.events import ExecutionContext, MessageEvent
from app.services.tasks import TaskService


class DeterministicLLM:
    """Substitui somente o provedor externo; o TaskAgent usado � o real."""

    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        del system_prompt, user_message
        return (
            '{"message":"Buscando suas tarefas.","command":{"type":"tasks.list",'
            '"payload":{}},"transition":null,"metadata":{}}'
        )


def make_context(*, user_id: UUID, idempotency_key: str) -> ExecutionContext:
    return ExecutionContext(
        user_id=user_id,
        graph_thread_id="task-list-thread",
        correlation_id=idempotency_key,
        idempotency_key=idempotency_key,
        source="test",
    )


@pytest.mark.asyncio
async def test_graph_lists_active_tasks_by_default(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    await service.create_task(
        make_context(user_id=user_id, idempotency_key="seed-active"),
        TaskCreatePayload(title="Tarefa pendente"),
    )
    completed = await service.create_task(
        make_context(user_id=user_id, idempotency_key="seed-completed"),
        TaskCreatePayload(title="Tarefa concluída"),
    )
    async with session_factory() as session:
        async with session.begin():
            completed_model = await session.get(Task, completed.task.id)
            assert completed_model is not None
            completed_model.status = "completed"

    registry = CommandRegistry()
    register_task_handlers(registry, service)
    graph = build_graph(
        task_agent=TaskAgent(DeterministicLLM()),
        harness=Harness(registry),
    )
    context = make_context(user_id=user_id, idempotency_key="list-active")
    event = MessageEvent(
        event_id="list-active-event",
        user_id=user_id,
        text="listar minhas tarefas",
        received_at=datetime.now(UTC),
        source="test",
    )

    result = await graph.ainvoke({"event": event, "context": context})

    assert result["harness_result"].status == "executed"
    assert result["harness_result"].effect["total"] == 1
    assert result["harness_result"].effect["items"][0]["title"] == "Tarefa pendente"
    assert result["response_decision"].message == "Encontrei 1 tarefa: Tarefa pendente."


@pytest.mark.asyncio
async def test_task_service_applies_status_and_due_date_filters(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    await service.create_task(
        make_context(user_id=user_id, idempotency_key="filter-active"),
        TaskCreatePayload(title="Tarefa desta semana", due_date=date(2026, 8, 20)),
    )
    completed = await service.create_task(
        make_context(user_id=user_id, idempotency_key="filter-completed"),
        TaskCreatePayload(title="Tarefa concluída", due_date=date(2026, 8, 21)),
    )
    async with session_factory() as session:
        async with session.begin():
            completed_model = await session.get(Task, completed.task.id)
            assert completed_model is not None
            completed_model.status = "completed"

    completed_result = await service.list_tasks(
        make_context(user_id=user_id, idempotency_key="list-completed"),
        TaskListPayload(status="completed"),
    )
    all_in_range = await service.list_tasks(
        make_context(user_id=user_id, idempotency_key="list-range"),
        TaskListPayload(
            status=None,
            due_date_from=date(2026, 8, 20),
            due_date_to=date(2026, 8, 21),
        ),
    )

    assert completed_result.total == 1
    assert completed_result.items[0].title == "Tarefa concluída"
    assert all_in_range.total == 2
    assert {item.title for item in all_in_range.items} == {
        "Tarefa desta semana",
        "Tarefa concluída",
    }
