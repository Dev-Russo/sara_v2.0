"""Entrada do webhook Telegram e envio da resposta pelo adapter de canal."""

from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import Settings
from app.integrations.telegram.delivery import TelegramResponseDelivery
from app.integrations.telegram.ingress import TelegramIngress
from app.integrations.telegram.messages import build_outgoing_message
from app.integrations.telegram.updates import (
    TelegramConfirmationUpdate,
    TelegramPayloadError,
    parse_telegram_update,
)
from app.schemas.events import ConfirmationEvent, ExecutionContext, MessageEvent
from app.schemas.results import HarnessResult, ResponseDecision

router = APIRouter(tags=["telegram"])


@router.post("/telegram", status_code=status.HTTP_202_ACCEPTED)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    """Valida, processa e entrega a resposta de um update Telegram."""

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

    delivery: TelegramResponseDelivery | None = request.app.state.telegram_delivery
    if delivery is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram delivery is unavailable",
        )

    if isinstance(update, TelegramConfirmationUpdate):
        try:
            await delivery.answer_callback_query(update.callback_query_id)
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Telegram callback acknowledgement failed",
            ) from error

    ingress: TelegramIngress = request.app.state.telegram_ingress
    ingress_result = await ingress.ingest(update)
    if ingress_result.status == "delivery_retry":
        pending_delivery = ingress_result.pending_delivery
        if pending_delivery is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Telegram delivery state is invalid",
            )
        try:
            await delivery.retry(pending_delivery)
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Telegram response delivery failed",
            ) from error
        return {"accepted": True}

    if ingress_result.status != "accepted" or ingress_result.event is None:
        return {"accepted": False}

    event = ingress_result.event
    context = _build_execution_context(event)
    graph_result = await graph.ainvoke({"event": event, "context": context})
    if not isinstance(graph_result, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Telegram response state is invalid",
        )
    response = graph_result.get("response_decision")
    if not isinstance(response, ResponseDecision):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Telegram response is unavailable",
        )

    harness_result = graph_result.get("harness_result")
    if harness_result is not None and not isinstance(harness_result, HarnessResult):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Telegram response state is invalid",
        )

    try:
        message = build_outgoing_message(
            response=response,
            harness_result=harness_result,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Telegram response is invalid",
        ) from error

    try:
        await delivery.deliver(
            update_id=update.update_id,
            user_id=event.user_id,
            chat_id=update.chat_id,
            message=message,
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Telegram response delivery failed",
        ) from error

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
