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
    def __init__(self, task_id: UUID) -> None:
        self.task_id = task_id

    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        del system_prompt, user_message
        return (
            '{"message":null,"command":{"type":"tasks.update",'
            f'"payload":{{"task_id":"{self.task_id}","title":"Preparar apresentação",'
            '"priority":1},"transition":null,"metadata":{}}}'
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
    created = await service.create_task(
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
        task_agent=TaskAgent(UpdateTaskLLM(created.task.id)),
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
        "Tarefa atualizada: Preparar apresentação. "
        f"Campos alterados: t{chr(0xED)}tulo e prioridade."
    )
