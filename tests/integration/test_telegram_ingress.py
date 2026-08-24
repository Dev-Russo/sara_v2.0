from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.telegram.ingress import TelegramIngressAdapter
from app.integrations.telegram.updates import (
    TelegramConfirmationUpdate,
    TelegramMessageUpdate,
)
from app.models.user import User
from app.schemas.events import ConfirmationEvent, MessageEvent


@pytest.mark.asyncio
async def test_ingress_maps_chat_to_trusted_user_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = uuid4()
    async with session_factory() as session:
        async with session.begin():
            session.add(User(id=user_id, telegram_chat_id="12345"))

    update = TelegramMessageUpdate(
        update_id=42,
        chat_id="12345",
        text="criar relatório",
        received_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
    )

    result = await TelegramIngressAdapter(session_factory).ingest(update)

    assert result.status == "accepted"
    assert isinstance(result.event, MessageEvent)
    assert result.event.event_id == "telegram:42"
    assert result.event.user_id == user_id
    assert result.event.text == "criar relatório"
    assert result.event.source == "telegram"


@pytest.mark.asyncio
async def test_ingress_rejects_unknown_chat(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    update = TelegramMessageUpdate(
        update_id=43,
        chat_id="unknown-chat",
        text="não autorizado",
        received_at=datetime(2026, 8, 24, 12, 1, tzinfo=UTC),
    )

    result = await TelegramIngressAdapter(session_factory).ingest(update)

    assert result.status == "unauthorized"
    assert result.event is None


@pytest.mark.asyncio
async def test_ingress_maps_confirmation_to_trusted_user_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = uuid4()
    async with session_factory() as session:
        async with session.begin():
            session.add(User(id=user_id, telegram_chat_id="12345"))

    confirmation_id = UUID("11111111-1111-1111-1111-111111111111")
    update = TelegramConfirmationUpdate(
        update_id=44,
        callback_query_id="callback-44",
        chat_id="12345",
        confirmation_id=confirmation_id,
        decision="confirm",
        received_at=datetime(2026, 8, 24, 12, 2, tzinfo=UTC),
    )

    result = await TelegramIngressAdapter(session_factory).ingest(update)

    assert result.status == "accepted"
    assert isinstance(result.event, ConfirmationEvent)
    assert result.event.confirmation_id == confirmation_id
    assert result.event.user_id == user_id
    assert result.event.decision == "confirm"


@pytest.mark.asyncio
async def test_ingress_deduplicates_the_same_update_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = uuid4()
    async with session_factory() as session:
        async with session.begin():
            session.add(User(id=user_id, telegram_chat_id="12345"))

    update = TelegramMessageUpdate(
        update_id=45,
        chat_id="12345",
        text="processar uma vez",
        received_at=datetime(2026, 8, 24, 12, 3, tzinfo=UTC),
    )
    service = TelegramIngressAdapter(session_factory)

    first = await service.ingest(update)
    second = await service.ingest(update)

    assert first.status == "accepted"
    assert second.status == "duplicate"
    assert second.event is None
