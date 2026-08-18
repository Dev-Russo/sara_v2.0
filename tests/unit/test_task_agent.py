from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.agents.task import TaskAgent
from app.schemas.commands import TasksCreateCommand
from app.schemas.events import ExecutionContext, MessageEvent


class FakeLLMClient:
    """Fake restrito aos testes; produção usa um adapter real."""

    def __init__(self, response: str) -> None:
        self.response = response

    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        return self.response


def make_event(text: str) -> MessageEvent:
    return MessageEvent(
        event_id="test-event",
        user_id=uuid4(),
        text=text,
        received_at=datetime.now(UTC),
        source="test",
    )


def make_context(user_id) -> ExecutionContext:
    return ExecutionContext(
        user_id=user_id,
        graph_thread_id="test-thread",
        correlation_id="test-correlation",
        idempotency_key="test-agent-command",
        source="test",
    )


@pytest.mark.asyncio
async def test_task_agent_validates_llm_decision() -> None:
    llm = FakeLLMClient(
        '{"message":"Criando tarefa.","command":{"type":"tasks.create",'
        '"payload":{"title":"Estudar arquitetura","priority":1}},'
        '"transition":null,"metadata":{}}',
    )
    event = make_event("estudar arquitetura")

    decision = await TaskAgent(llm).decide(event, make_context(event.user_id))

    assert isinstance(decision.command, TasksCreateCommand)
    assert decision.command.payload.title == "Estudar arquitetura"
    assert decision.command.payload.priority == 1


@pytest.mark.asyncio
async def test_task_agent_rejects_invalid_llm_output_without_command() -> None:
    llm = FakeLLMClient("não é JSON")
    event = make_event("qualquer coisa")

    decision = await TaskAgent(llm).decide(event, make_context(event.user_id))

    assert decision.command is None
    assert decision.message == "Não consegui interpretar essa solicitação."
    assert decision.metadata["error_code"] == "AGENT_OUTPUT_INVALID"

