"""Implementação SQLAlchemy do UserRepository."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.interfaces import UserRepository


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_exists(self, user_id: UUID) -> None:
        user = await self._session.get(User, user_id)
        if user is None:
            self._session.add(User(id=user_id))
            await self._session.flush()
