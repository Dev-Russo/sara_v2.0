"""Orquestra persistÃªncia e entrega de respostas Telegram."""

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.telegram.adapter import TelegramDeliveryError, TelegramGateway
from app.integrations.telegram.messages import TelegramOutgoingMessage
from app.repositories.telegram_delivery_repository import SqlAlchemyTelegramDeliveryRepository
from app.schemas.telegram import TelegramDeliveryData


class TelegramResponseDelivery(Protocol):
    async def deliver(
        self,
        *,
        update_id: int,
        user_id: UUID,
        chat_id: str,
        message: TelegramOutgoingMessage,
    ) -> None:
        """Persiste e envia uma resposta nova."""

    async def retry(self, delivery: TelegramDeliveryData) -> None:
        """Reenvia somente uma resposta jÃ¡ persistida como pendente."""

    async def answer_callback_query(self, callback_query_id: str) -> None:
        """Reconhece um callback sem executar nenhuma regra de domÃ­nio."""


class TelegramDeliveryService(TelegramResponseDelivery):
    """MantÃ©m entrega externa separada da execuÃ§Ã£o do comando de domÃ­nio."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        gateway: TelegramGateway,
    ) -> None:
        self._session_factory = session_factory
        self._gateway = gateway

    async def deliver(
        self,
        *,
        update_id: int,
        user_id: UUID,
        chat_id: str,
        message: TelegramOutgoingMessage,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                repository = SqlAlchemyTelegramDeliveryRepository(session)
                delivery = await repository.create_pending(
                    update_id=update_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    text=message.text,
                    reply_markup=message.reply_markup,
                )

        await self._attempt(delivery)

    async def retry(self, delivery: TelegramDeliveryData) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                repository = SqlAlchemyTelegramDeliveryRepository(session)
                current = await repository.get_pending_for_update(
                    update_id=delivery.update_id,
                    user_id=delivery.user_id,
                )
        if current is not None:
            await self._attempt(current)

    async def answer_callback_query(self, callback_query_id: str) -> None:
        await self._gateway.answer_callback_query(callback_query_id)

    async def _attempt(self, delivery: TelegramDeliveryData) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                repository = SqlAlchemyTelegramDeliveryRepository(session)
                await repository.mark_attempt(
                    update_id=delivery.update_id,
                    user_id=delivery.user_id,
                )

        try:
            await self._gateway.send_message(
                delivery.chat_id,
                delivery.message.text,
                delivery.message.reply_markup,
            )
        except Exception as error:
            error_code = (
                error.code
                if isinstance(error, TelegramDeliveryError)
                else "TELEGRAM_DELIVERY_FAILED"
            )
            async with self._session_factory() as session:
                async with session.begin():
                    repository = SqlAlchemyTelegramDeliveryRepository(session)
                    await repository.mark_failed(
                        update_id=delivery.update_id,
                        user_id=delivery.user_id,
                        error_code=error_code,
                    )
            raise

        async with self._session_factory() as session:
            async with session.begin():
                repository = SqlAlchemyTelegramDeliveryRepository(session)
                await repository.mark_delivered(
                    update_id=delivery.update_id,
                    user_id=delivery.user_id,
                )
