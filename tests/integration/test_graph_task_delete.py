from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.task import TaskAgent
from app.graph.builder import build_graph
from app.harness.handlers import build_task_confirmation_resolver, register_task_handlers
from app.harness.registry import CommandRegistry
from app.harness.service import Harness
from app.schemas.commands import TaskCreatePayload
from app.schemas.events import ConfirmationEvent, ExecutionContext, MessageEvent
from app.services.tasks import TaskService


class DeleteTaskLLM:
    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        del system_prompt, user_message
        return (
            '{"message":null,"command":{"type":"tasks.delete",'
            '"payload":{"query":"apagar relatório"}},'
            '"transition":null,"metadata":{}}'
        )


class AmbiguousDeleteTaskLLM:
    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        del system_prompt, user_message
        return (
            '{"message":null,"command":{"type":"tasks.delete",'
            '"payload":{"query":"academia"}},'
            '"transition":null,"metadata":{}}'
        )


def make_context(*, user_id: UUID, key: str) -> ExecutionContext:
    return ExecutionContext(
        user_id=user_id,
        graph_thread_id="graph-task-delete-thread",
        correlation_id=key,
        idempotency_key=key,
        source="test",
    )


def make_graph(service: TaskService, agent: TaskAgent):
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    harness = Harness(
        registry,
        confirmation_resolver=build_task_confirmation_resolver(service),
    )
    return build_graph(task_agent=agent, harness=harness)


@pytest.mark.asyncio
async def test_graph_resumes_task_delete_after_confirmation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(
        session_factory,
        clock=lambda: datetime(2026, 8, 21, 12, tzinfo=UTC),
    )
    user_id = uuid4()
    await service.create_task(
        make_context(user_id=user_id, key="graph-delete-create"),
        TaskCreatePayload(title="Apagar relatório"),
    )
    graph = make_graph(service, TaskAgent(DeleteTaskLLM()))

    pending = await graph.ainvoke(
        {
            "event": MessageEvent(
                event_id="graph-delete-event",
                user_id=user_id,
                text="exclua apagar relatório",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(user_id=user_id, key="graph-delete-request"),
        },
    )

    assert pending["harness_result"].status == "awaiting_confirmation"
    assert pending["response_decision"].message == (
        "Confirma a exclusão da tarefa \"Apagar relatório\"? "
        "Essa ação não poderá ser desfeita."
    )
    confirmation_id = pending["harness_result"].confirmation_id

    prompt = await graph.ainvoke(
        {
            "event": MessageEvent(
                event_id="graph-delete-invalid-confirmation",
                user_id=user_id,
                text="talvez",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(user_id=user_id, key="graph-delete-invalid-confirmation"),
            "active_flow": "task",
            "pending_confirmation_id": confirmation_id,
        },
    )

    assert prompt["response_decision"].message == (
        "Responda \"sim\" para confirmar ou \"n\u00e3o\" para cancelar."
    )

    confirmed = await graph.ainvoke(
        {
            "event": ConfirmationEvent(
                confirmation_id=confirmation_id,
                user_id=user_id,
                decision="confirm",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(user_id=user_id, key="graph-delete-confirm"),
        },
    )

    assert confirmed["harness_result"].status == "executed"
    assert confirmed["response_decision"].message == "Tarefa excluída: Apagar relatório."


@pytest.mark.asyncio
async def test_graph_selects_ambiguous_task_before_requesting_confirmation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    await service.create_task(
        make_context(user_id=user_id, key="graph-delete-first"),
        TaskCreatePayload(title="Ir à academia de manhã"),
    )
    second = await service.create_task(
        make_context(user_id=user_id, key="graph-delete-second"),
        TaskCreatePayload(title="Ir à academia à noite"),
    )
    graph = make_graph(service, TaskAgent(AmbiguousDeleteTaskLLM()))

    pending = await graph.ainvoke(
        {
            "event": MessageEvent(
                event_id="graph-delete-ambiguous",
                user_id=user_id,
                text="exclua academia",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(user_id=user_id, key="graph-delete-ambiguous-key"),
        },
    )

    assert pending["harness_result"].status == "awaiting_selection"
    assert pending["pending_task_delete"].query == "academia"
    assert "Qual delas deseja excluir?" in pending["response_decision"].message

    selected = await graph.ainvoke(
        {
            "event": MessageEvent(
                event_id="graph-delete-selection",
                user_id=user_id,
                text="a segunda",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(user_id=user_id, key="graph-delete-selection-key"),
            "pending_task_candidates": pending["pending_task_candidates"],
            "pending_task_delete": pending["pending_task_delete"],
        },
    )

    assert selected["resolved_command"].type == "tasks.delete_by_id"
    assert selected["harness_result"].status == "awaiting_confirmation"
    assert selected["harness_result"].effect["task_id"] == str(second.task.id)
