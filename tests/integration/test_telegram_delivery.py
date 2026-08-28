from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.telegram.delivery import TelegramDeliveryService
from app.integrations.telegram.ingress import TelegramIngressAdapter
from app.integrations.telegram.messages import TelegramOutgoingMessage
from app.integrations.telegram.updates import TelegramMessageUpdate
from app.models.telegram_delivery import TelegramDelivery
from app.models.user import User


class FailingThenWorkingGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.failed = False

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: object | None = None,
    ) -> None:
        del reply_markup
        self.calls.append((chat_id, text))
        if not self.failed:
            self.failed = True
            raise RuntimeError("temporary Telegram failure")


@pytest.mark.asyncio
async def test_failed_delivery_is_replayed_without_reexecuting_ingress_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = uuid4()
    async with session_factory() as session:
        async with session.begin():
            session.add(User(id=user_id, telegram_chat_id="12345"))

    update = TelegramMessageUpdate(
        update_id=99,
        chat_id="12345",
        text="criar tarefa",
        received_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
    )
    ingress = TelegramIngressAdapter(session_factory)
    first = await ingress.ingest(update)
    assert first.status == "accepted"

    gateway = FailingThenWorkingGateway()
    delivery = TelegramDeliveryService(session_factory, gateway)
    message = TelegramOutgoingMessage(text="Tarefa criada: Comprar leite.")

    with pytest.raises(RuntimeError, match="temporary Telegram failure"):
        await delivery.deliver(
            update_id=update.update_id,
            user_id=user_id,
            chat_id=update.chat_id,
            message=message,
        )

    retry = await ingress.ingest(update)
    assert retry.status == "delivery_retry"
    assert retry.event is None
    assert retry.pending_delivery is not None

    await delivery.retry(retry.pending_delivery)
    duplicate = await ingress.ingest(update)
    assert duplicate.status == "duplicate"
    assert duplicate.pending_delivery is None
    assert gateway.calls == [
        ("12345", "Tarefa criada: Comprar leite."),
        ("12345", "Tarefa criada: Comprar leite."),
    ]

    async with session_factory() as session:
        stored = await session.scalar(
            select(TelegramDelivery).where(TelegramDelivery.update_id == 99),
        )

    assert stored is not None
    assert stored.status == "delivered"
    assert stored.attempts == 2
