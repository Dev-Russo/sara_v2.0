from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.task import TaskAgent
from app.graph.builder import build_graph
from app.harness.handlers import register_task_handlers
from app.harness.registry import CommandRegistry
from app.harness.service import Harness
from app.schemas.commands import TaskCreatePayload
from app.schemas.events import ExecutionContext, MessageEvent
from app.services.tasks import TaskService


class UpdateTaskLLM:
    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        del system_prompt, user_message
        return (
            '{"message":null,"command":{"type":"tasks.update",'
            '"payload":{"query":"Preparar rascunho","title":"Preparar apresenta\\u00e7\\u00e3o",'
            '"priority":1},"transition":null,"metadata":{}}}'
        )


class AmbiguousUpdateTaskLLM:
    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        del system_prompt, user_message
        return (
            '{"message":null,"command":{"type":"tasks.update",'
            '"payload":{"query":"academia","priority":1},'
            '"transition":null,"metadata":{}}}'
        )


def make_context(*, user_id: UUID) -> ExecutionContext:
    return ExecutionContext(
        user_id=user_id,
        graph_thread_id="graph-task-update-thread",
        correlation_id="graph-task-update-correlation",
        idempotency_key="graph-task-update-command",
        source="test",
    )


@pytest.mark.asyncio
async def test_graph_executes_task_update_from_agent_through_harness(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    harness = Harness(registry)
    user_id = uuid4()
    await service.create_task(
        ExecutionContext(
            user_id=user_id,
            graph_thread_id="graph-task-update-create",
            correlation_id="graph-task-update-create",
            idempotency_key="graph-task-update-create",
            source="test",
        ),
        TaskCreatePayload(title="Preparar rascunho"),
    )
    graph = build_graph(
        task_agent=TaskAgent(UpdateTaskLLM()),
        harness=harness,
    )

    result = await graph.ainvoke(
        {
            "event": MessageEvent(
                event_id="graph-task-update-event",
                user_id=user_id,
                text="altere a tarefa",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(user_id=user_id),
        },
    )

    assert result["agent_decision"].command.type == "tasks.update"
    assert result["harness_result"].status == "executed"
    assert result["harness_result"].effect["kind"] == "task_updated"
    assert result["harness_result"].effect["changed_fields"] == ["title", "priority"]
    assert result["response_decision"].message == (
        "Tarefa atualizada: Preparar apresenta\u00e7\u00e3o. "
        f"Campos alterados: t{chr(0xED)}tulo e prioridade."
    )


@pytest.mark.asyncio
async def test_graph_resolves_ambiguous_update_after_user_selects_candidate(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    await service.create_task(
        ExecutionContext(
            user_id=user_id,
            graph_thread_id="graph-ambiguous-update-first",
            correlation_id="graph-ambiguous-update-first",
            idempotency_key="graph-ambiguous-update-first",
            source="test",
        ),
        TaskCreatePayload(title="Ir \u00e0 academia de manh\u00e3"),
    )
    second = await service.create_task(
        ExecutionContext(
            user_id=user_id,
            graph_thread_id="graph-ambiguous-update-second",
            correlation_id="graph-ambiguous-update-second",
            idempotency_key="graph-ambiguous-update-second",
            source="test",
        ),
        TaskCreatePayload(title="Ir \u00e0 academia \u00e0 noite"),
    )
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    graph = build_graph(
        task_agent=TaskAgent(AmbiguousUpdateTaskLLM()),
        harness=Harness(registry),
    )

    first_result = await graph.ainvoke(
        {
            "event": MessageEvent(
                event_id="graph-ambiguous-update-event",
                user_id=user_id,
                text="mude academia para prioridade alta",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(user_id=user_id),
        },
    )

    assert first_result["harness_result"].status == "awaiting_selection"
    assert first_result["pending_task_update"].query == "academia"
    assert first_result["response_decision"].message == (
        "Encontrei mais de uma tarefa: 1. Ir \u00e0 academia de manh\u00e3; "
        "2. Ir \u00e0 academia \u00e0 noite. Qual delas deseja atualizar?"
    )

    selected_result = await graph.ainvoke(
        {
            "event": MessageEvent(
                event_id="graph-ambiguous-update-selection",
                user_id=user_id,
                text="a segunda",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(user_id=user_id),
            "pending_task_candidates": first_result["pending_task_candidates"],
            "pending_task_update": first_result["pending_task_update"],
        },
    )

    assert selected_result["harness_result"].command_type == "tasks.update_by_id"
    assert selected_result["harness_result"].effect["task_id"] == str(second.task.id)
    assert selected_result["harness_result"].effect["changed_fields"] == ["priority"]
