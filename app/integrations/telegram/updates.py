"""Parsing determinístico dos updates recebidos pelo Telegram."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TelegramPayloadError(ValueError):
    """Indica que um update reconhecido não respeita o contrato esperado."""


class TelegramMessageUpdate(BaseModel):
    """Mensagem de texto recebida em um chat privado."""

    update_id: int = Field(ge=0)
    chat_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    received_at: datetime


class TelegramConfirmationUpdate(BaseModel):
    """Callback de confirmação recebido em um chat privado."""

    update_id: int = Field(ge=0)
    callback_query_id: str = Field(min_length=1)
    chat_id: str = Field(min_length=1)
    confirmation_id: UUID
    decision: Literal["confirm", "cancel"]
    received_at: datetime


TelegramUpdate = TelegramMessageUpdate | TelegramConfirmationUpdate


def parse_telegram_update(
    payload: object,
    *,
    received_at: datetime,
) -> TelegramUpdate | None:
    """Converte um payload do Telegram em um update interno validado."""

    if not isinstance(payload, dict):
        raise TelegramPayloadError("telegram payload must be an object")

    update_id = _required_update_id(payload)
    update_shapes = [key for key in ("message", "callback_query") if key in payload]
    if len(update_shapes) > 1:
        raise TelegramPayloadError("telegram payload contains multiple update shapes")
    if not update_shapes:
        return None

    shape = update_shapes[0]
    raw_update = payload[shape]
    if not isinstance(raw_update, dict):
        raise TelegramPayloadError(f"telegram {shape} must be an object")

    if shape == "message":
        return _parse_message_update(update_id, raw_update, received_at)
    return _parse_confirmation_update(update_id, raw_update, received_at)


def _parse_message_update(
    update_id: int,
    raw_message: dict[object, object],
    received_at: datetime,
) -> TelegramMessageUpdate | None:
    chat_id = _private_chat_id(raw_message)
    if chat_id is None:
        return None

    if "text" not in raw_message:
        return None
    text = raw_message["text"]
    if not isinstance(text, str) or not text.strip():
        raise TelegramPayloadError("telegram message text must be a non-empty string")

    return TelegramMessageUpdate(
        update_id=update_id,
        chat_id=chat_id,
        text=text.strip(),
        received_at=received_at,
    )


def _parse_confirmation_update(
    update_id: int,
    raw_callback: dict[object, object],
    received_at: datetime,
) -> TelegramConfirmationUpdate | None:
    chat_id = _private_chat_id(raw_callback, nested_key="message")
    if chat_id is None:
        return None

    callback_query_id = raw_callback.get("id")
    data = raw_callback.get("data")
    if not isinstance(callback_query_id, str) or not callback_query_id:
        raise TelegramPayloadError("telegram callback query id is required")
    if not isinstance(data, str):
        raise TelegramPayloadError("telegram callback data is required")

    confirmation_id, decision = _parse_confirmation_data(data)
    return TelegramConfirmationUpdate(
        update_id=update_id,
        callback_query_id=callback_query_id,
        chat_id=chat_id,
        confirmation_id=confirmation_id,
        decision=decision,
        received_at=received_at,
    )


def _required_update_id(payload: dict[object, object]) -> int:
    update_id = payload.get("update_id")
    if isinstance(update_id, bool) or not isinstance(update_id, int) or update_id < 0:
        raise TelegramPayloadError("telegram update_id must be a non-negative integer")
    return update_id


def _private_chat_id(
    raw_update: dict[object, object],
    *,
    nested_key: str | None = None,
) -> str | None:
    chat_container: object = raw_update
    if nested_key is not None:
        chat_container = raw_update.get(nested_key)
        if not isinstance(chat_container, dict):
            raise TelegramPayloadError("telegram callback message is required")

    raw_chat = chat_container.get("chat")
    if not isinstance(raw_chat, dict):
        raise TelegramPayloadError("telegram chat is required")
    if raw_chat.get("type") != "private":
        return None

    chat_id = raw_chat.get("id")
    if isinstance(chat_id, bool) or not isinstance(chat_id, int):
        raise TelegramPayloadError("telegram private chat id must be an integer")
    return str(chat_id)


def _parse_confirmation_data(data: str) -> tuple[UUID, Literal["confirm", "cancel"]]:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "confirmation":
        raise TelegramPayloadError("telegram callback data has an invalid format")

    decision = parts[1]
    if decision not in {"confirm", "cancel"}:
        raise TelegramPayloadError("telegram callback decision is invalid")
    try:
        confirmation_id = UUID(parts[2])
    except ValueError as error:
        raise TelegramPayloadError("telegram confirmation id is invalid") from error
    return confirmation_id, decision
