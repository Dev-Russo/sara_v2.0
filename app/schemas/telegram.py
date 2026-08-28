"""Contratos tipados para a entrega de mensagens pelo Telegram."""

from typing import Literal, TypedDict
from uuid import UUID

from pydantic import BaseModel, Field


class TelegramInlineKeyboardButton(TypedDict):
    text: str
    callback_data: str


class TelegramReplyMarkup(TypedDict):
    inline_keyboard: list[list[TelegramInlineKeyboardButton]]


class TelegramOutgoingMessage(BaseModel):
    """Mensagem pronta para o protocolo de saída do Telegram."""

    text: str = Field(min_length=1, max_length=4096)
    reply_markup: TelegramReplyMarkup | None = None


class TelegramDeliveryData(BaseModel):
    """Snapshot persistido para repetir somente a entrega externa."""

    delivery_id: UUID
    update_id: int = Field(ge=0)
    user_id: UUID
    chat_id: str = Field(min_length=1)
    message: TelegramOutgoingMessage
    status: Literal["pending", "delivered"]
    attempts: int = Field(ge=0)
    last_error_code: str | None = None
