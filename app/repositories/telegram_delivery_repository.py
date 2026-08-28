"""Repository assÃ­ncrono para snapshots de entrega Telegram."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telegram_delivery import TelegramDelivery
from app.repositories.interfaces import TelegramDeliveryRepository
from app.schemas.telegram import TelegramDeliveryData, TelegramOutgoingMessage, TelegramReplyMarkup


class SqlAlchemyTelegramDeliveryRepository(TelegramDeliveryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending(
        self,
        *,
        update_id: int,
        user_id: UUID,
        chat_id: str,
        text: str,
        reply_markup: TelegramReplyMarkup | None,
    ) -> TelegramDeliveryData:
        delivery = TelegramDelivery(
            update_id=update_id,
            user_id=user_id,
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            status="pending",
            attempts=0,
        )
        self._session.add(delivery)
        await self._session.flush()
        return _to_data(delivery)

    async def get_pending_for_update(
        self,
        *,
        update_id: int,
        user_id: UUID,
    ) -> TelegramDeliveryData | None:
        result = await self._session.scalar(
            select(TelegramDelivery).where(
                TelegramDelivery.update_id == update_id,
                TelegramDelivery.user_id == user_id,
                TelegramDelivery.status == "pending",
            ),
        )
        return _to_data(result) if result is not None else None

    async def mark_attempt(self, *, update_id: int, user_id: UUID) -> None:
        await self._session.execute(
            update(TelegramDelivery)
            .where(
                TelegramDelivery.update_id == update_id,
                TelegramDelivery.user_id == user_id,
                TelegramDelivery.status == "pending",
            )
            .values(
                attempts=TelegramDelivery.attempts + 1,
                last_attempt_at=datetime.now(UTC),
                last_error_code=None,
            ),
        )

    async def mark_failed(
        self,
        *,
        update_id: int,
        user_id: UUID,
        error_code: str,
    ) -> None:
        await self._session.execute(
            update(TelegramDelivery)
            .where(
                TelegramDelivery.update_id == update_id,
                TelegramDelivery.user_id == user_id,
                TelegramDelivery.status == "pending",
            )
            .values(last_error_code=error_code),
        )

    async def mark_delivered(self, *, update_id: int, user_id: UUID) -> None:
        await self._session.execute(
            update(TelegramDelivery)
            .where(
                TelegramDelivery.update_id == update_id,
                TelegramDelivery.user_id == user_id,
                TelegramDelivery.status == "pending",
            )
            .values(
                status="delivered",
                delivered_at=datetime.now(UTC),
                last_error_code=None,
            ),
        )


def _to_data(delivery: TelegramDelivery) -> TelegramDeliveryData:
    return TelegramDeliveryData(
        delivery_id=delivery.delivery_id,
        update_id=delivery.update_id,
        user_id=delivery.user_id,
        chat_id=delivery.chat_id,
        message=TelegramOutgoingMessage(
            text=delivery.text,
            reply_markup=delivery.reply_markup,
        ),
        status=delivery.status,
        attempts=delivery.attempts,
        last_error_code=delivery.last_error_code,
    )
