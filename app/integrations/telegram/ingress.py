"""Entrada confiável de updates Telegram antes do Graph."""

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.telegram.updates import (
    TelegramConfirmationUpdate,
    TelegramMessageUpdate,
    TelegramUpdate,
)
from app.repositories.processed_update_repository import SqlAlchemyProcessedUpdateRepository
from app.repositories.telegram_delivery_repository import SqlAlchemyTelegramDeliveryRepository
from app.repositories.user_repository import SqlAlchemyUserRepository
from app.schemas.events import ConfirmationEvent, MessageEvent
from app.schemas.telegram import TelegramDeliveryData

IngressStatus = Literal["accepted", "duplicate", "unauthorized", "delivery_retry"]
InternalEvent = MessageEvent | ConfirmationEvent


class TelegramIngress(Protocol):
    """Seam usada pela borda HTTP para validar e deduplicar updates."""

    async def ingest(self, update: TelegramUpdate) -> "TelegramIngressResult":
        """Converte um update validado em evento interno quando autorizado."""


class TelegramIngressResult(BaseModel):
    """Resultado estruturado de identidade, deduplicação e retry de entrega."""

    status: IngressStatus
    user_id: UUID | None = None
    event: InternalEvent | None = None
    pending_delivery: TelegramDeliveryData | None = None


class TelegramIngressAdapter:
    """Mapeia updates autorizados para eventos internos sem executar o Graph."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def ingest(self, update: TelegramUpdate) -> TelegramIngressResult:
        async with self._session_factory() as session:
            async with session.begin():
                user_repository = SqlAlchemyUserRepository(session)
                user_id = await user_repository.get_id_by_telegram_chat_id(update.chat_id)

                if user_id is None:
                    return TelegramIngressResult(status="unauthorized")

                event_type, event = _build_internal_event(update, user_id)
                processed_repository = SqlAlchemyProcessedUpdateRepository(session)
                is_new = await processed_repository.record_if_new(
                    update_id=update.update_id,
                    user_id=user_id,
                    telegram_chat_id=update.chat_id,
                    event_type=event_type,
                    received_at=update.received_at,
                )
                if not is_new:
                    pending_delivery = await SqlAlchemyTelegramDeliveryRepository(
                        session,
                    ).get_pending_for_update(
                        update_id=update.update_id,
                        user_id=user_id,
                    )
                    if pending_delivery is not None:
                        return TelegramIngressResult(
                            status="delivery_retry",
                            user_id=user_id,
                            pending_delivery=pending_delivery,
                        )
                    return TelegramIngressResult(status="duplicate", user_id=user_id)

                return TelegramIngressResult(
                    status="accepted",
                    user_id=user_id,
                    event=event,
                )


def _build_internal_event(update: TelegramUpdate, user_id: UUID) -> tuple[str, InternalEvent]:
    if isinstance(update, TelegramMessageUpdate):
        return (
            "message",
            MessageEvent(
                event_id=f"telegram:{update.update_id}",
                user_id=user_id,
                text=update.text,
                received_at=update.received_at,
                source="telegram",
            ),
        )

    if isinstance(update, TelegramConfirmationUpdate):
        return (
            "confirmation",
            ConfirmationEvent(
                confirmation_id=update.confirmation_id,
                user_id=user_id,
                decision=update.decision,
                received_at=update.received_at,
                source="telegram",
            ),
        )

    raise TypeError(f"unsupported Telegram update: {type(update).__name__}")
