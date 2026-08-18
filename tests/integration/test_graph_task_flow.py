from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.task import TaskAgent
from app.graph.builder import build_graph
from app.harness.handlers import register_task_handlers
from app.harness.registry import CommandRegistry
from app.harness.service import Harness
from app.schemas.events import ExecutionContext, MessageEvent
from app.services.tasks import TaskService


class DeterministicLLM:
    """Substitui somente o provedor externo; o TaskAgent usado é o real."""

    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        del system_prompt, user_message
        return (
            '{"message":"Criando tarefa.","command":{"type":"tasks.create",'
            '"payload":{"title":"Preparar apresentação","priority":1}},'
            '"transition":null,"metadata":{}}'
        )


def make_event(*, user_id) -> MessageEvent:
    return MessageEvent(
        event_id="graph-task-event",
        user_id=user_id,
        text="preparar apresentação amanhã",
        received_at=datetime.now(UTC),
        source="test",
    )


def make_context(*, user_id) -> ExecutionContext:
    return ExecutionContext(
        user_id=user_id,
        graph_thread_id="graph-task-thread",
        correlation_id="graph-task-correlation",
        idempotency_key="graph-task-command",
        source="test",
    )


@pytest.mark.asyncio
async def test_graph_executes_task_agent_command_through_harness(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    harness = Harness(registry)
    user_id = uuid4()
    graph = build_graph(
        task_agent=TaskAgent(DeterministicLLM()),
        harness=harness,
    )

    result = await graph.ainvoke(
        {
            "event": make_event(user_id=user_id),
            "context": make_context(user_id=user_id),
        },
    )

    assert result["active_flow"] == "task"
    assert result["agent_decision"].command.type == "tasks.create"
    assert result["harness_result"].status == "executed"
    assert result["harness_result"].effect["title"] == "Preparar apresentação"
    assert result["response_decision"].message == "Tarefa criada: Preparar apresentação."
