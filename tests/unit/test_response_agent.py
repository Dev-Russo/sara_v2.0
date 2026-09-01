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

    assert decision.message == "Não foi possível executar esse comando."


@pytest.mark.asyncio
async def test_response_agent_verbalizes_task_update_effect() -> None:
    result = HarnessResult(
        status="executed",
        command_id=uuid4(),
        command_type="tasks.update",
        effect={
            "kind": "task_updated",
            "task_id": str(uuid4()),
            "title": "Revisar documento final",
            "changed_fields": ["title", "priority", "description"],
        },
    )

    decision = await DeterministicResponseAgent().respond(result, make_context())

    assert decision.message == (
        "Tarefa atualizada: Revisar documento final. "
        "Campos alterados: t" + chr(0xED) + "tulo, prioridade e descri"
        + chr(0xE7) + chr(0xE3) + "o."
    )


@pytest.mark.asyncio
async def test_response_agent_uses_safe_fallback_for_incomplete_task_update_effect() -> None:
    result = HarnessResult(
        status="executed",
        command_id=uuid4(),
        command_type="tasks.update",
        effect={"title": "Tarefa sem efeito"},
    )

    decision = await DeterministicResponseAgent().respond(result, make_context())

    assert decision.message == "N\u00e3o consegui confirmar essa atualiza\u00e7\u00e3o."


@pytest.mark.asyncio
async def test_response_agent_asks_confirmation_before_task_deletion() -> None:
    result = HarnessResult(
        status="awaiting_confirmation",
        command_id=uuid4(),
        command_type="tasks.delete",
        confirmation_id=uuid4(),
        effect={"kind": "task_delete_pending", "title": "Apagar relatório"},
    )

    decision = await DeterministicResponseAgent().respond(result, make_context())

    assert decision.message == (
        "Confirma a exclusão da tarefa \"Apagar relatório\"? "
        "Essa ação não poderá ser desfeita."
    )


@pytest.mark.asyncio
async def test_response_agent_explains_expired_task_deletion_confirmation() -> None:
    result = HarnessResult(
        status="failed",
        command_id=uuid4(),
        command_type="tasks.delete",
        error_code="CONFIRMATION_EXPIRED",
    )

    decision = await DeterministicResponseAgent().respond(result, make_context())

    assert decision.message == (
        "A confirma\u00e7\u00e3o expirou. Posso preparar a exclus\u00e3o novamente."
    )


@pytest.mark.asyncio
async def test_response_agent_confirms_task_deletion_only_after_execution() -> None:
    result = HarnessResult(
        status="executed",
        command_id=uuid4(),
        command_type="tasks.delete",
        effect={"kind": "task_deleted", "title": "Apagar relatório"},
    )

    decision = await DeterministicResponseAgent().respond(result, make_context())

    assert decision.message == "Tarefa excluída: Apagar relatório."
