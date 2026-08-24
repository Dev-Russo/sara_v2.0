"""Persistence seam for Telegram update deduplication."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.processed_update import ProcessedUpdate
from app.repositories.interfaces import ProcessedUpdateRepository


class SqlAlchemyProcessedUpdateRepository(ProcessedUpdateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_if_new(
        self,
        *,
        update_id: int,
        user_id: UUID,
        telegram_chat_id: str,
        event_type: str,
        received_at: datetime,
    ) -> bool:
        try:
            async with self._session.begin_nested():
                self._session.add(
                    ProcessedUpdate(
                        update_id=update_id,
                        user_id=user_id,
                        telegram_chat_id=telegram_chat_id,
                        event_type=event_type,
                        received_at=received_at,
                        status="received",
                    ),
                )
                await self._session.flush()
        except IntegrityError:
            return False
        return True
