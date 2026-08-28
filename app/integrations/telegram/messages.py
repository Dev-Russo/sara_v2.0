"""Conversão de resultados estruturados em mensagens do canal."""

from app.integrations.telegram.keyboards import build_confirmation_keyboard
from app.schemas.results import HarnessResult, ResponseDecision
from app.schemas.telegram import TelegramOutgoingMessage

__all__ = ["TelegramOutgoingMessage", "build_outgoing_message"]


def build_outgoing_message(
    *,
    response: ResponseDecision,
    harness_result: HarnessResult | None,
) -> TelegramOutgoingMessage:
    """Converte a resposta do Graph em uma mensagem do protocolo Telegram."""

    reply_markup = None
    if harness_result is not None and harness_result.status == "awaiting_confirmation":
        if harness_result.confirmation_id is None:
            raise ValueError("awaiting confirmation result must contain confirmation_id")
        reply_markup = build_confirmation_keyboard(harness_result.confirmation_id)

    return TelegramOutgoingMessage(
        text=response.message,
        reply_markup=reply_markup,
    )
