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


class DeterministicLLM:
    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        del system_prompt, user_message
        return (
            '{"message":null,"command":{"type":"tasks.complete",'
            '"payload":{"query":"academia"}},'
            '"transition":null,"metadata":{}}'
        )


class NoMatchLLM:
    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        del system_prompt, user_message
        return (
            '{"message":null,"command":{"type":"tasks.complete",'
            '"payload":{"query":"inexistente"}},'
            '"transition":null,"metadata":{}}'
        )


def make_context(*, user_id: UUID, idempotency_key: str) -> ExecutionContext:
    return ExecutionContext(
        user_id=user_id,
        graph_thread_id="graph-completion-thread",
        correlation_id=idempotency_key,
        idempotency_key=idempotency_key,
        source="test",
    )


@pytest.mark.asyncio
async def test_graph_searches_pending_task_and_completes_single_candidate(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    created = await service.create_task(
        make_context(user_id=user_id, idempotency_key="graph-completion-create"),
        TaskCreatePayload(title="Ir à academia"),
    )
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    graph = build_graph(task_agent=TaskAgent(DeterministicLLM()), harness=Harness(registry))

    result = await graph.ainvoke(
        {
            "event": MessageEvent(
                event_id="graph-completion-event",
                user_id=user_id,
                text="marque academia como concluída",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(user_id=user_id, idempotency_key="graph-completion-turn"),
        },
    )

    assert result["agent_decision"].command.type == "tasks.complete"
    assert result["harness_result"].command_type == "tasks.complete"
    assert result["harness_result"].status == "executed"
    assert result["harness_result"].effect["task_id"] == str(created.task.id)
    assert result["response_decision"].message == "Tarefa concluída: Ir à academia."


@pytest.mark.asyncio
async def test_graph_keeps_multiple_task_candidates_pending(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    first = await service.create_task(
        make_context(user_id=user_id, idempotency_key="graph-ambiguous-first"),
        TaskCreatePayload(title="Ir à academia de manhã"),
    )
    second = await service.create_task(
        make_context(user_id=user_id, idempotency_key="graph-ambiguous-second"),
        TaskCreatePayload(title="Ir à academia à noite"),
    )
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    graph = build_graph(task_agent=TaskAgent(DeterministicLLM()), harness=Harness(registry))

    result = await graph.ainvoke(
        {
            "event": MessageEvent(
                event_id="graph-ambiguous-event",
                user_id=user_id,
                text="marque academia como concluída",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(user_id=user_id, idempotency_key="graph-ambiguous-turn"),
        },
    )

    assert result["harness_result"].command_type == "tasks.complete"
    assert result["harness_result"].status == "awaiting_selection"
    assert {candidate.id for candidate in result["pending_task_candidates"]} == {
        first.task.id,
        second.task.id,
    }
    assert result["response_decision"].message == (
        "Encontrei mais de uma tarefa: 1. Ir à academia de manhã; "
        "2. Ir à academia à noite. Qual delas deseja concluir?"
    )


@pytest.mark.asyncio
async def test_graph_completes_candidate_selected_by_number(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    await service.create_task(
        make_context(user_id=user_id, idempotency_key="graph-choice-first"),
        TaskCreatePayload(title="Ir à academia de manhã"),
    )
    second = await service.create_task(
        make_context(user_id=user_id, idempotency_key="graph-choice-second"),
        TaskCreatePayload(title="Ir à academia à noite"),
    )
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    graph = build_graph(task_agent=TaskAgent(DeterministicLLM()), harness=Harness(registry))
    first_result = await graph.ainvoke(
        {
            "event": MessageEvent(
                event_id="graph-choice-search-event",
                user_id=user_id,
                text="marque academia como concluída",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(user_id=user_id, idempotency_key="graph-choice-search"),
        },
    )

    selected_result = await graph.ainvoke(
        {
            "event": MessageEvent(
                event_id="graph-choice-selection-event",
                user_id=user_id,
                text="a segunda",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(user_id=user_id, idempotency_key="graph-choice-selection"),
            "pending_task_candidates": first_result["pending_task_candidates"],
        },
    )

    assert selected_result["harness_result"].command_type == "tasks.complete_by_id"
    assert selected_result["harness_result"].effect["task_id"] == str(second.task.id)
    assert selected_result["response_decision"].message == (
        "Tarefa concluída: Ir à academia à noite."
    )


@pytest.mark.asyncio
async def test_graph_reports_when_pending_task_search_has_no_candidates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    graph = build_graph(task_agent=TaskAgent(NoMatchLLM()), harness=Harness(registry))
    user_id = uuid4()

    result = await graph.ainvoke(
        {
            "event": MessageEvent(
                event_id="graph-no-match-event",
                user_id=user_id,
                text="marque a tarefa inexistente como concluída",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(user_id=user_id, idempotency_key="graph-no-match-turn"),
        },
    )

    assert result["harness_result"].command_type == "tasks.complete"
    assert result["harness_result"].effect["total"] == 0
    assert result["response_decision"].message == (
        "Não encontrei essa tarefa pendente. Pode descrever melhor a tarefa?"
    )
