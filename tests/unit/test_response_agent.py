from uuid import uuid4

import pytest

from app.agents.response import DeterministicResponseAgent
from app.schemas.events import ExecutionContext
from app.schemas.results import HarnessResult


def make_context() -> ExecutionContext:
    return ExecutionContext(
        user_id=uuid4(),
        graph_thread_id="response-test-thread",
        correlation_id="response-test-correlation",
        idempotency_key="response-test-idempotency",
        source="test",
    )


@pytest.mark.asyncio
async def test_response_agent_verbalizes_task_list_effect() -> None:
    result = HarnessResult(
        status="executed",
        command_id=uuid4(),
        command_type="tasks.list",
        effect={
            "kind": "tasks_listed",
            "items": [{"title": "Tarefa pendente"}],
            "total": 1,
        },
    )

    decision = await DeterministicResponseAgent().respond(result, make_context())

    assert decision.message == "Encontrei 1 tarefa: Tarefa pendente."


@pytest.mark.asyncio
async def test_response_agent_does_not_claim_success_for_rejected_command() -> None:
    result = HarnessResult(
        status="rejected",
        command_id=uuid4(),
        command_type="tasks.create",
        error_code="COMMAND_NOT_SUPPORTED",
    )

    decision = await DeterministicResponseAgent().respond(result, make_context())

    assert decision.message == "NÃ£o foi possÃ­vel executar esse comando."
