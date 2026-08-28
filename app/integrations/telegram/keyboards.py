"""Construção de teclados de confirmação do Telegram."""

from uuid import UUID

from app.schemas.telegram import TelegramReplyMarkup


def build_confirmation_keyboard(confirmation_id: UUID) -> TelegramReplyMarkup:
    """Cria callbacks compatíveis com o parser de confirmações recebido."""

    return {
        "inline_keyboard": [
            [
                {
                    "text": "Confirmar",
                    "callback_data": f"confirmation:confirm:{confirmation_id}",
                },
                {
                    "text": "Cancelar",
                    "callback_data": f"confirmation:cancel:{confirmation_id}",
                },
            ],
        ],
    }
