from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.integrations.telegram.updates import (
    TelegramConfirmationUpdate,
    TelegramMessageUpdate,
    TelegramPayloadError,
    parse_telegram_update,
)

RECEIVED_AT = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def test_parse_private_text_update() -> None:
    payload = {
        "update_id": 42,
        "message": {
            "chat": {"id": 12345, "type": "private"},
            "text": "  criar relatório  ",
            "user_id": "must-not-cross-the-adapter",
        },
    }

    result = parse_telegram_update(payload, received_at=RECEIVED_AT)

    assert result == TelegramMessageUpdate(
        update_id=42,
        chat_id="12345",
        text="criar relatório",
        received_at=RECEIVED_AT,
    )
    assert "user_id" not in TelegramMessageUpdate.model_fields


def test_ignore_group_message() -> None:
    result = parse_telegram_update(
        {
            "update_id": 43,
            "message": {
                "chat": {"id": -12345, "type": "group"},
                "text": "não processar grupo",
            },
        },
        received_at=RECEIVED_AT,
    )

    assert result is None


def test_ignore_private_media_without_text() -> None:
    result = parse_telegram_update(
        {
            "update_id": 44,
            "message": {
                "chat": {"id": 12345, "type": "private"},
                "photo": [{"file_id": "photo-id"}],
            },
        },
        received_at=RECEIVED_AT,
    )

    assert result is None


def test_reject_empty_message_text() -> None:
    with pytest.raises(TelegramPayloadError):
        parse_telegram_update(
            {
                "update_id": 45,
                "message": {
                    "chat": {"id": 12345, "type": "private"},
                    "text": "   ",
                },
            },
            received_at=RECEIVED_AT,
        )


def test_parse_confirmation_callback() -> None:
    confirmation_id = uuid4()
    result = parse_telegram_update(
        {
            "update_id": 46,
            "callback_query": {
                "id": "callback-46",
                "data": f"confirmation:confirm:{confirmation_id}",
                "message": {
                    "chat": {"id": 12345, "type": "private"},
                },
            },
        },
        received_at=RECEIVED_AT,
    )

    assert result == TelegramConfirmationUpdate(
        update_id=46,
        callback_query_id="callback-46",
        chat_id="12345",
        confirmation_id=confirmation_id,
        decision="confirm",
        received_at=RECEIVED_AT,
    )


def test_parse_confirmation_cancel_callback() -> None:
    confirmation_id = UUID("11111111-1111-1111-1111-111111111111")
    result = parse_telegram_update(
        {
            "update_id": 47,
            "callback_query": {
                "id": "callback-47",
                "data": f"confirmation:cancel:{confirmation_id}",
                "message": {
                    "chat": {"id": 12345, "type": "private"},
                },
            },
        },
        received_at=RECEIVED_AT,
    )

    assert isinstance(result, TelegramConfirmationUpdate)
    assert result.decision == "cancel"
    assert result.confirmation_id == confirmation_id


@pytest.mark.parametrize(
    "data",
    [
        "confirmation:confirm:not-a-uuid",
        "confirmation:maybe:11111111-1111-1111-1111-111111111111",
        "other:confirm:11111111-1111-1111-1111-111111111111",
    ],
)
def test_reject_invalid_confirmation_callback(data: str) -> None:
    with pytest.raises(TelegramPayloadError):
        parse_telegram_update(
            {
                "update_id": 48,
                "callback_query": {
                    "id": "callback-48",
                    "data": data,
                    "message": {
                        "chat": {"id": 12345, "type": "private"},
                    },
                },
            },
            received_at=RECEIVED_AT,
        )


def test_reject_missing_update_id() -> None:
    with pytest.raises(TelegramPayloadError):
        parse_telegram_update(
            {
                "message": {
                    "chat": {"id": 12345, "type": "private"},
                    "text": "sem update id",
                },
            },
            received_at=RECEIVED_AT,
        )
