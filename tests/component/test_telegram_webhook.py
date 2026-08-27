from dataclasses import dataclass, field
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.integrations.telegram.ingress import IngressStatus, TelegramIngressResult
from app.integrations.telegram.updates import (
    TelegramMessageUpdate,
    TelegramUpdate,
)
from app.main import create_app
from app.schemas.events import ConfirmationEvent, MessageEvent

SECRET = "webhook-secret"


@dataclass
class RecordingIngress:
    status: IngressStatus = "accepted"
    user_id: UUID = field(default_factory=uuid4)
    calls: list[TelegramUpdate] = field(default_factory=list)

    async def ingest(self, update: TelegramUpdate) -> TelegramIngressResult:
        self.calls.append(update)
        if self.status != "accepted":
            return TelegramIngressResult(status=self.status)

        if isinstance(update, TelegramMessageUpdate):
            event = MessageEvent(
                event_id=f"telegram:{update.update_id}",
                user_id=self.user_id,
                text=update.text,
                received_at=update.received_at,
                source="telegram",
            )
        else:
            event = ConfirmationEvent(
                confirmation_id=update.confirmation_id,
                user_id=self.user_id,
                decision=update.decision,
                received_at=update.received_at,
                source="telegram",
            )
        return TelegramIngressResult(status="accepted", event=event)


@dataclass
class RecordingGraph:
    calls: list[dict[str, object]] = field(default_factory=list)

    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        self.calls.append(state)
        return state


def make_client(
    ingress: RecordingIngress,
    graph: RecordingGraph,
) -> TestClient:
    application = create_app(
        settings=Settings(telegram_webhook_secret=SECRET),
        graph=graph,  # type: ignore[arg-type]
        telegram_ingress=ingress,  # type: ignore[arg-type]
    )
    return TestClient(application)


def message_payload(*, update_id: int = 42) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": 12345, "type": "private"},
            "text": "criar tarefa",
        },
    }


def webhook_headers() -> dict[str, str]:
    return {"X-Telegram-Bot-Api-Secret-Token": SECRET}


def test_webhook_forwards_accepted_message_to_graph() -> None:
    ingress = RecordingIngress()
    graph = RecordingGraph()
    client = make_client(ingress, graph)

    response = client.post(
        "/webhooks/telegram",
        json=message_payload(),
        headers=webhook_headers(),
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert len(ingress.calls) == 1
    assert len(graph.calls) == 1

    state = graph.calls[0]
    event = state["event"]
    context = state["context"]
    assert isinstance(event, MessageEvent)
    assert event.user_id == ingress.user_id
    assert event.text == "criar tarefa"
    assert context.user_id == ingress.user_id
    assert context.graph_thread_id == f"telegram:{ingress.user_id}"
    assert context.correlation_id == "telegram:42"
    assert context.idempotency_key == "telegram:42"
    assert context.source == "telegram"


def test_webhook_does_not_forward_duplicate_update_to_graph() -> None:
    ingress = RecordingIngress(status="duplicate")
    graph = RecordingGraph()
    client = make_client(ingress, graph)

    response = client.post(
        "/webhooks/telegram",
        json=message_payload(),
        headers=webhook_headers(),
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": False}
    assert len(graph.calls) == 0


def test_webhook_does_not_forward_unauthorized_update_to_graph() -> None:
    ingress = RecordingIngress(status="unauthorized")
    graph = RecordingGraph()
    client = make_client(ingress, graph)

    response = client.post(
        "/webhooks/telegram",
        json=message_payload(),
        headers=webhook_headers(),
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": False}
    assert len(graph.calls) == 0


def test_webhook_does_not_forward_unsupported_update_to_graph() -> None:
    ingress = RecordingIngress()
    graph = RecordingGraph()
    client = make_client(ingress, graph)

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 43,
            "message": {
                "chat": {"id": -12345, "type": "group"},
                "text": "não processar",
            },
        },
        headers=webhook_headers(),
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": False}
    assert len(ingress.calls) == 0
    assert len(graph.calls) == 0


def test_webhook_forwards_accepted_confirmation_to_graph() -> None:
    ingress = RecordingIngress()
    graph = RecordingGraph()
    client = make_client(ingress, graph)
    confirmation_id = "11111111-1111-1111-1111-111111111111"

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 44,
            "callback_query": {
                "id": "callback-44",
                "data": f"confirmation:confirm:{confirmation_id}",
                "message": {
                    "chat": {"id": 12345, "type": "private"},
                },
            },
        },
        headers=webhook_headers(),
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert len(graph.calls) == 1
    assert isinstance(graph.calls[0]["event"], ConfirmationEvent)
    assert graph.calls[0]["context"].idempotency_key == (
        f"telegram:confirmation:{confirmation_id}:confirm"
    )


def test_webhook_does_not_record_update_when_graph_is_unavailable() -> None:
    ingress = RecordingIngress()
    application = create_app(
        settings=Settings(
            telegram_webhook_secret=SECRET,
            llm_api_key="",
            llm_model="",
        ),
        telegram_ingress=ingress,  # type: ignore[arg-type]
    )
    client = TestClient(application)

    response = client.post(
        "/webhooks/telegram",
        json=message_payload(),
        headers=webhook_headers(),
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Telegram graph is unavailable"}
    assert len(ingress.calls) == 0


def test_webhook_rejects_invalid_secret() -> None:
    client = make_client(RecordingIngress(), RecordingGraph())

    response = client.post(
        "/webhooks/telegram",
        json=message_payload(),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )

    assert response.status_code == 403
