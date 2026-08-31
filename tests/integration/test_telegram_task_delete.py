from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.task import TaskAgent
from app.config import Settings
from app.graph.builder import build_graph
from app.graph.checkpoint import PersistentGraphRunner
from app.harness.handlers import build_task_confirmation_resolver, register_task_handlers
from app.harness.registry import CommandRegistry
from app.harness.service import Harness
from app.integrations.telegram.delivery import TelegramDeliveryService
from app.integrations.telegram.ingress import TelegramIngressAdapter
from app.main import create_app
from app.models.user import User
from app.schemas.commands import TaskCreatePayload, TaskListPayload
from app.schemas.events import ExecutionContext
from app.schemas.telegram import TelegramReplyMarkup
from app.services.tasks import TaskService


class DeleteTaskLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        del system_prompt, user_message
        self.calls += 1
        return (
            '{"message":null,"command":{"type":"tasks.delete",'
            '"payload":{"query":"Apagar relatório"}},'
            '"transition":null,"metadata":{}}'
        )


@dataclass
class RecordingTelegramGateway:
    messages: list[tuple[str, str, TelegramReplyMarkup | None]] = field(default_factory=list)
    callback_query_ids: list[str] = field(default_factory=list)

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: TelegramReplyMarkup | None = None,
    ) -> None:
        self.messages.append((chat_id, text, reply_markup))

    async def answer_callback_query(self, callback_query_id: str) -> None:
        self.callback_query_ids.append(callback_query_id)


def make_context(*, user_id: UUID, key: str) -> ExecutionContext:
    return ExecutionContext(
        user_id=user_id,
        graph_thread_id=f"telegram:{user_id}",
        correlation_id=key,
        idempotency_key=key,
        source="test",
    )


async def create_user(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: UUID,
) -> None:
    async with session_factory() as session:
        async with session.begin():
            session.add(User(id=user_id, telegram_chat_id="12345"))


def build_test_graph(
    session_factory: async_sessionmaker[AsyncSession],
    llm: DeleteTaskLLM,
    *,
    clock: Callable[[], datetime] | None = None,
) -> PersistentGraphRunner:
    service = TaskService(session_factory, clock=clock)
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    harness = Harness(
        registry,
        confirmation_resolver=build_task_confirmation_resolver(service),
    )
    graph = build_graph(task_agent=TaskAgent(llm), harness=harness)
    return PersistentGraphRunner(graph, session_factory)


def build_application(
    session_factory: async_sessionmaker[AsyncSession],
    llm: DeleteTaskLLM,
    gateway: RecordingTelegramGateway,
    *,
    clock: Callable[[], datetime] | None = None,
):
    return create_app(
        settings=Settings(telegram_webhook_secret="webhook-secret"),
        graph=build_test_graph(session_factory, llm, clock=clock),
        telegram_ingress=TelegramIngressAdapter(session_factory),
        telegram_delivery=TelegramDeliveryService(session_factory, gateway),
    )


def message_payload(*, update_id: int, text: str) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": 12345, "type": "private"},
            "text": text,
        },
    }


def confirmation_payload(*, update_id: int, callback_data: str) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"callback-{update_id}",
            "data": callback_data,
            "message": {"chat": {"id": 12345, "type": "private"}},
        },
    }


@pytest.mark.asyncio
async def test_telegram_deletion_survives_runner_restart_and_delivers_effect(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = uuid4()
    await create_user(session_factory, user_id)
    task_service = TaskService(session_factory)
    await task_service.create_task(
        make_context(user_id=user_id, key="telegram-delete-create"),
        TaskCreatePayload(title="Apagar relatório"),
    )
    llm = DeleteTaskLLM()
    gateway = RecordingTelegramGateway()
    ingress = TelegramIngressAdapter(session_factory)
    runner = build_test_graph(session_factory, llm)
    application = create_app(
        settings=Settings(telegram_webhook_secret="webhook-secret"),
        graph=runner,
        telegram_ingress=ingress,
        telegram_delivery=TelegramDeliveryService(session_factory, gateway),
    )

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first_response = await client.post(
            "/webhooks/telegram",
            json=message_payload(update_id=100, text="exclua o relatório"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        )

        assert first_response.status_code == 202
        assert gateway.messages[-1][1] == (
            'Confirma a exclusão da tarefa "Apagar relatório"? Essa ação não poderá ser desfeita.'
        )
        markup = gateway.messages[-1][2]
        assert markup is not None
        callback_data = markup["inline_keyboard"][0][0]["callback_data"]
        confirmation_id = UUID(callback_data.rsplit(":", maxsplit=1)[1])
        persisted = await runner.get_continuation(
            graph_thread_id=f"telegram:{user_id}",
            user_id=user_id,
        )
        assert persisted.pending_confirmation_id == confirmation_id

        application.state.graph = build_test_graph(session_factory, llm)
        second_response = await client.post(
            "/webhooks/telegram",
            json=confirmation_payload(update_id=101, callback_data=callback_data),
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        )

    assert second_response.status_code == 202
    assert gateway.callback_query_ids == ["callback-101"]
    assert gateway.messages[-1][1] == "Tarefa excluída: Apagar relatório."
    assert llm.calls == 1

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        duplicate_response = await client.post(
            "/webhooks/telegram",
            json=confirmation_payload(update_id=102, callback_data=callback_data),
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        )

    assert duplicate_response.status_code == 202
    assert gateway.messages[-1][1] == "A tarefa já estava excluída: Apagar relatório."
    assert llm.calls == 1

    remaining = await task_service.list_tasks(
        make_context(user_id=user_id, key="telegram-delete-list"),
        TaskListPayload(status="active"),
    )
    assert remaining.items == []
    continuation = await application.state.graph.get_continuation(
        graph_thread_id=f"telegram:{user_id}",
        user_id=user_id,
    )
    assert continuation.pending_confirmation_id is None
    assert continuation.active_flow == "task"


@pytest.mark.asyncio
async def test_telegram_deletion_can_be_cancelled_without_mutating_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = uuid4()
    await create_user(session_factory, user_id)
    task_service = TaskService(session_factory)
    await task_service.create_task(
        make_context(user_id=user_id, key="telegram-cancel-create"),
        TaskCreatePayload(title="Apagar relatório"),
    )
    gateway = RecordingTelegramGateway()
    application = build_application(session_factory, DeleteTaskLLM(), gateway)

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/webhooks/telegram",
            json=message_payload(update_id=110, text="exclua o relatório"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        )
        markup = gateway.messages[-1][2]
        assert markup is not None
        cancel_data = markup["inline_keyboard"][0][1]["callback_data"]

        response = await client.post(
            "/webhooks/telegram",
            json=confirmation_payload(update_id=111, callback_data=cancel_data),
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        )

    assert response.status_code == 202
    assert gateway.messages[-1][1] == "Exclusão cancelada."
    remaining = await task_service.list_tasks(
        make_context(user_id=user_id, key="telegram-cancel-list"),
        TaskListPayload(status="active"),
    )
    assert len(remaining.items) == 1


@pytest.mark.asyncio
async def test_telegram_expired_deletion_returns_controlled_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = uuid4()
    await create_user(session_factory, user_id)
    current_time = [datetime(2026, 8, 31, 12, tzinfo=UTC)]
    task_service = TaskService(session_factory, clock=lambda: current_time[0])
    await task_service.create_task(
        make_context(user_id=user_id, key="telegram-expired-create"),
        TaskCreatePayload(title="Apagar relatório"),
    )
    gateway = RecordingTelegramGateway()
    application = build_application(
        session_factory,
        DeleteTaskLLM(),
        gateway,
        clock=lambda: current_time[0],
    )

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/webhooks/telegram",
            json=message_payload(update_id=120, text="exclua o relatório"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        )
        markup = gateway.messages[-1][2]
        assert markup is not None
        confirm_data = markup["inline_keyboard"][0][0]["callback_data"]
        current_time[0] += timedelta(minutes=11)

        response = await client.post(
            "/webhooks/telegram",
            json=confirmation_payload(update_id=121, callback_data=confirm_data),
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        )

    assert response.status_code == 202
    assert gateway.messages[-1][1] == (
        "A confirmação expirou. Posso preparar a exclusão novamente."
    )
    remaining = await task_service.list_tasks(
        make_context(user_id=user_id, key="telegram-expired-list"),
        TaskListPayload(status="active"),
    )
    assert len(remaining.items) == 1
