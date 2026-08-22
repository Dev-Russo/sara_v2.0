"""Persistência de confirmações e consumo atômico de pendências."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.confirmation_request import ConfirmationRequest


class SqlAlchemyConfirmationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending(
        self,
        *,
        user_id: UUID,
        execution_id: UUID,
        command_id: UUID,
        command_type: str,
        payload_snapshot: dict[str, object],
        summary: str,
        expires_at: datetime,
    ) -> ConfirmationRequest:
        request = ConfirmationRequest(
            user_id=user_id,
            execution_id=execution_id,
            command_id=command_id,
            command_type=command_type,
            payload_snapshot=payload_snapshot,
            summary=summary,
            status="pending",
            expires_at=expires_at,
        )
        self._session.add(request)
        await self._session.flush()
        return request

    async def get_for_user(
        self,
        user_id: UUID,
        confirmation_id: UUID,
    ) -> ConfirmationRequest | None:
        return await self._session.scalar(
            select(ConfirmationRequest).where(
                ConfirmationRequest.id == confirmation_id,
                ConfirmationRequest.user_id == user_id,
            ),
        )

    async def transition_pending(
        self,
        *,
        user_id: UUID,
        confirmation_id: UUID,
        status: str,
        resolved_at: datetime,
    ) -> bool:
        result = await self._session.execute(
            update(ConfirmationRequest)
            .where(
                ConfirmationRequest.id == confirmation_id,
                ConfirmationRequest.user_id == user_id,
                ConfirmationRequest.status == "pending",
            )
            .values(status=status, resolved_at=resolved_at),
        )
        return result.rowcount == 1
