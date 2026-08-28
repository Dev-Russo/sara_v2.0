from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.task import TaskAgent
from app.cli import CliSession
from app.graph.builder import build_graph
from app.graph.checkpoint import PersistentGraphRunner
from app.harness.handlers import register_task_handlers
from app.harness.registry import CommandRegistry
from app.harness.service import Harness
from app.schemas.commands import TaskCreatePayload
from app.schemas.events import ExecutionContext
from app.services.tasks import TaskService


class CompletionDeterministicLLM:
    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        del system_prompt, user_message
        return (
            '{"message":null,"command":{"type":"tasks.complete",'
            '"payload":{"query":"academia"}},'
            '"transition":null,"metadata":{}}'
        )


def make_context(*, user_id: UUID, idempotency_key: str) -> ExecutionContext:
    return ExecutionContext(
        user_id=user_id,
        graph_thread_id="cli-completion-thread",
        correlation_id=idempotency_key,
        idempotency_key=idempotency_key,
        source="test",
    )


@pytest.mark.asyncio
async def test_cli_session_keeps_ambiguous_task_candidates_for_next_turn(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    await service.create_task(
        make_context(user_id=user_id, idempotency_key="cli-seed-first"),
        TaskCreatePayload(title="Ir à academia de manhã"),
    )
    await service.create_task(
        make_context(user_id=user_id, idempotency_key="cli-seed-second"),
        TaskCreatePayload(title="Ir à academia à noite"),
    )
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    graph = build_graph(
        task_agent=TaskAgent(CompletionDeterministicLLM()),
        harness=Harness(registry),
    )
    runner = PersistentGraphRunner(graph, session_factory)
    trace: list[str] = []
    session = CliSession(
        graph=runner,
        user_id=user_id,
        debug=True,
        trace_sink=trace.append,
    )

    ambiguous = await session.process("marque academia como concluída")
    completed = await session.process("a segunda")

    assert ambiguous == (
        "Encontrei mais de uma tarefa: 1. Ir à academia de manhã; "
        "2. Ir à academia à noite. Qual delas deseja concluir?"
    )
    assert completed == "Tarefa concluída: Ir à academia à noite."
    assert any(line.startswith("[debug] resolved_command: ") for line in trace)
    assert any('"type": "tasks.complete"' in line for line in trace)
