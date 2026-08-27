"""Entrada do webhook Telegram; o processamento será encaminhado ao Graph."""

from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import Settings
from app.integrations.telegram.ingress import TelegramIngress
from app.integrations.telegram.updates import TelegramPayloadError, parse_telegram_update
from app.schemas.events import ConfirmationEvent, ExecutionContext, MessageEvent

router = APIRouter(tags=["telegram"])


@router.post("/telegram", status_code=status.HTTP_202_ACCEPTED)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    """Valida, autoriza e encaminha um update Telegram ao Graph."""

    settings: Settings = request.app.state.settings
    expected_secret = settings.telegram_webhook_secret
    if expected_secret and x_telegram_bot_api_secret_token != expected_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid webhook secret")

    try:
        payload = await request.json()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid Telegram payload",
        ) from error

    try:
        update = parse_telegram_update(payload, received_at=datetime.now(UTC))
    except TelegramPayloadError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid Telegram update",
        ) from error

    if update is None:
        return {"accepted": False}

    graph = request.app.state.graph
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram graph is unavailable",
        )

    ingress: TelegramIngress = request.app.state.telegram_ingress
    ingress_result = await ingress.ingest(update)
    if ingress_result.status != "accepted" or ingress_result.event is None:
        return {"accepted": False}

    event = ingress_result.event
    context = _build_execution_context(event)
    await graph.ainvoke({"event": event, "context": context})
    return {"accepted": True}


def _build_execution_context(event: MessageEvent | ConfirmationEvent) -> ExecutionContext:
    """Cria contexto confiável sem aceitar identidade do payload Telegram."""

    event_key = _event_key(event)
    return ExecutionContext(
        user_id=event.user_id,
        graph_thread_id=f"telegram:{event.user_id}",
        correlation_id=event_key,
        idempotency_key=event_key,
        source="telegram",
    )


def _event_key(event: MessageEvent | ConfirmationEvent) -> str:
    if isinstance(event, MessageEvent):
        return event.event_id
    return f"telegram:confirmation:{event.confirmation_id}:{event.decision}"
