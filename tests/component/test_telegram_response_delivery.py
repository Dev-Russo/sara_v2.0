from dataclasses import dataclass, field
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.integrations.telegram.delivery import TelegramResponseDelivery
from app.integrations.telegram.ingress import (
    TelegramIngress,
    TelegramIngressResult,
)
from app.integrations.telegram.messages import TelegramOutgoingMessage
from app.integrations.telegram.updates import TelegramUpdate
from app.main import create_app
from app.schemas.events import ConfirmationEvent, MessageEvent
from app.schemas.results import ResponseDecision
from app.schemas.telegram import TelegramDeliveryData


@dataclass
class RecordingIngress:
    result: TelegramIngressResult
    calls: list[TelegramUpdate] = field(default_factory=list)

    async def ingest(self, update: TelegramUpdate) -> TelegramIngressResult:
        self.calls.append(update)
        return self.result


@dataclass
class RecordingGraph:
    calls: list[dict[str, object]] = field(default_factory=list)

    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        self.calls.append(state)
        return {
            **state,
            "response_decision": ResponseDecision(message="Tarefa criada: Comprar leite."),
        }


@dataclass
class RecordingDelivery(TelegramResponseDelivery):
    calls: list[tuple[int, UUID, str, TelegramOutgoingMessage]] = field(default_factory=list)
    retries: list[TelegramDeliveryData] = field(default_factory=list)
    callback_query_ids: list[str] = field(default_factory=list)
    fail: bool = False

    async def deliver(
        self,
        *,
        update_id: int,
        user_id: UUID,
        chat_id: str,
        message: TelegramOutgoingMessage,
    ) -> None:
        self.calls.append((update_id, user_id, chat_id, message))
        if self.fail:
            raise RuntimeError("delivery failed")

    async def retry(self, delivery: TelegramDeliveryData) -> None:
        self.retries.append(delivery)

    async def answer_callback_query(self, callback_query_id: str) -> None:
        self.callback_query_ids.append(callback_query_id)


def message_payload(*, update_id: int = 42) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": 12345, "type": "private"},
            "text": "criar tarefa",
        },
    }


def make_client(
    ingress: TelegramIngress,
    graph: RecordingGraph,
    delivery: TelegramResponseDelivery,
    *,
    raise_server_exceptions: bool = True,
) -> TestClient:
    application = create_app(
        settings=Settings(telegram_webhook_secret="webhook-secret"),
        graph=graph,  # type: ignore[arg-type]
        telegram_ingress=ingress,
        telegram_delivery=delivery,
    )
    return TestClient(application, raise_server_exceptions=raise_server_exceptions)


def test_webhook_delivers_graph_response_to_the_trusted_chat() -> None:
    user_id = uuid4()
    ingress = RecordingIngress(
        TelegramIngressResult(
            status="accepted",
            event=MessageEvent(
                event_id="telegram:42",
                user_id=user_id,
                text="criar tarefa",
                received_at="2026-08-27T12:00:00Z",
                source="telegram",
            ),
        ),
    )
    graph = RecordingGraph()
    delivery = RecordingDelivery()

    response = make_client(ingress, graph, delivery).post(
        "/webhooks/telegram",
        json=message_payload(),
        headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert len(graph.calls) == 1
    assert delivery.calls[0][0:3] == (42, user_id, "12345")
    assert delivery.calls[0][3].text == "Tarefa criada: Comprar leite."


def test_webhook_retries_pending_delivery_without_running_graph() -> None:
    user_id = uuid4()
    pending = TelegramDeliveryData(
        delivery_id=uuid4(),
        update_id=42,
        user_id=user_id,
        chat_id="12345",
        message=TelegramOutgoingMessage(text="Tarefa criada."),
        status="pending",
        attempts=1,
    )
    ingress = RecordingIngress(
        TelegramIngressResult(status="delivery_retry", pending_delivery=pending),
    )
    graph = RecordingGraph()
    delivery = RecordingDelivery()

    response = make_client(ingress, graph, delivery).post(
        "/webhooks/telegram",
        json=message_payload(),
        headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert graph.calls == []
    assert delivery.retries == [pending]


def test_webhook_returns_controlled_error_when_delivery_fails() -> None:
    user_id = uuid4()
    ingress = RecordingIngress(
        TelegramIngressResult(
            status="accepted",
            event=MessageEvent(
                event_id="telegram:42",
                user_id=user_id,
                text="criar tarefa",
                received_at="2026-08-27T12:00:00Z",
                source="telegram",
            ),
        ),
    )
    response = make_client(
        ingress,
        RecordingGraph(),
        RecordingDelivery(fail=True),
        raise_server_exceptions=False,
    ).post(
        "/webhooks/telegram",
        json=message_payload(),
        headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Telegram response delivery failed"}


def test_webhook_acknowledges_confirmation_callback() -> None:
    user_id = uuid4()
    delivery = RecordingDelivery()
    ingress = RecordingIngress(
        TelegramIngressResult(
            status="accepted",
            event=ConfirmationEvent(
                confirmation_id=uuid4(),
                user_id=user_id,
                decision="confirm",
                received_at="2026-08-27T12:00:00Z",
                source="telegram",
            ),
        ),
    )
    response = make_client(
        ingress,
        RecordingGraph(),
        delivery,
    ).post(
        "/webhooks/telegram",
        json={
            "update_id": 44,
            "callback_query": {
                "id": "callback-44",
                "data": "confirmation:confirm:11111111-1111-1111-1111-111111111111",
                "message": {"chat": {"id": 12345, "type": "private"}},
            },
        },
        headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
    )

    assert response.status_code == 202
    assert delivery.callback_query_ids == ["callback-44"]
