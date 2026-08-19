from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.task import TaskAgent
from app.cli import CliSession
from app.graph.builder import build_graph
from app.harness.handlers import register_task_handlers
from app.harness.registry import CommandRegistry
from app.harness.service import Harness
from app.services.tasks import TaskService


class DeterministicLLM:
    """Substitui somente o provedor externo; o TaskAgent usado é o real."""

    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        del system_prompt, user_message
        return (
            '{"message":"Criando tarefa.","command":{"type":"tasks.create",'
            '"payload":{"title":"Comprar café","priority":0}},'
            '"transition":null,"metadata":{}}'
        )


@pytest.mark.asyncio
async def test_cli_session_processes_message_through_real_task_agent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    graph = build_graph(
        task_agent=TaskAgent(DeterministicLLM()),
        harness=Harness(registry),
    )
    session = CliSession(graph=graph, user_id=uuid4())

    response = await session.process("comprar café")

    assert response == "Tarefa criada: Comprar café."
    assert session.active_flow == "task"


@pytest.mark.asyncio
async def test_cli_session_debug_trace_exposes_graph_decision_and_result(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    graph = build_graph(
        task_agent=TaskAgent(DeterministicLLM()),
        harness=Harness(registry),
    )
    trace: list[str] = []
    session = CliSession(
        graph=graph,
        user_id=uuid4(),
        debug=True,
        trace_sink=trace.append,
    )

    response = await session.process("comprar café")

    assert response == "Tarefa criada: Comprar café."
    assert any(line.startswith("[debug] agent_decision: ") for line in trace)
    assert any('"type": "tasks.create"' in line for line in trace)
    assert any(line.startswith("[debug] harness_result: ") for line in trace)
    assert any('"status": "executed"' in line for line in trace)
    assert trace[-1] == "[debug] response: Tarefa criada: Comprar café."
