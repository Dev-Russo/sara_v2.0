from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.agents.task import TaskAgent
from app.schemas.commands import (
    TasksCompleteCommand,
    TasksCreateCommand,
    TasksListCommand,
    TasksUpdateCommand,
)
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


@pytest.mark.asyncio
async def test_task_agent_does_not_force_completion_from_message_only() -> None:
    llm = FakeLLMClient(
        '{"message":"Preciso de mais detalhes.","command":null,'
        '"transition":null,"metadata":{}}',
    )
    event = make_event("marque uma tarefa como concluída")

    decision = await TaskAgent(llm).decide(event, make_context(event.user_id))

    assert decision.command is None
    assert decision.message == "Preciso de mais detalhes."


@pytest.mark.asyncio
async def test_task_agent_normalizes_today_for_task_listing() -> None:
    llm = FakeLLMClient(
        '{"message":null,"command":{"type":"tasks.list",'
        '"payload":{"status":"active","due_date_from":"2026-08-19",'
        '"due_date_to":"2026-08-19"}},"transition":null,"metadata":{}}',
    )
    event = MessageEvent(
        event_id="today-list-event",
        user_id=uuid4(),
        text="liste minhas tarefas de hoje",
        received_at=datetime(2026, 8, 18, 23, 0, tzinfo=UTC),
        source="test",
    )

    decision = await TaskAgent(llm).decide(event, make_context(event.user_id))

    assert isinstance(decision.command, TasksListCommand)
    assert decision.command.payload.due_date_from.isoformat() == "2026-08-18"
    assert decision.command.payload.due_date_to.isoformat() == "2026-08-18"


@pytest.mark.asyncio
async def test_task_agent_uses_complete_intent_for_description() -> None:
    llm = FakeLLMClient(
        '{"message":null,"command":{"type":"tasks.complete",'
        '"payload":{"query":"academia"}},'
        '"transition":null,"metadata":{}}',
    )
    event = make_event("marque academia como concluída")

    decision = await TaskAgent(llm).decide(event, make_context(event.user_id))

    assert isinstance(decision.command, TasksCompleteCommand)
    assert decision.command.payload.query == "academia"


@pytest.mark.asyncio
async def test_task_agent_uses_update_intent_without_schedule_fields() -> None:
    llm = FakeLLMClient(
        '{"message":null,"command":{"type":"tasks.update",'
        '"payload":{"query":"Estudar contratos","title":"Estudar contratos",'
        '"priority":1},"transition":null,"metadata":{}}}',
    )
    event = MessageEvent(
        event_id="update-task-event",
        user_id=uuid4(),
        text="altere estudar contratos para amanhã",
        received_at=datetime(2026, 8, 18, 23, 0, tzinfo=UTC),
        source="test",
    )

    decision = await TaskAgent(llm).decide(event, make_context(event.user_id))

    assert isinstance(decision.command, TasksUpdateCommand)
    assert decision.command.payload.query == "Estudar contratos"
    assert decision.command.payload.title == "Estudar contratos"
    assert decision.command.payload.priority == 1
    assert "due_date" not in decision.command.payload.model_fields_set
