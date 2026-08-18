"""Persistência da chave de idempotência de comandos."""


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.command_execution import CommandExecution
from app.schemas.events import ExecutionContext


class SqlAlchemyCommandExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_idempotency_key(self, key: str) -> CommandExecution | None:
        return await self._session.scalar(
            select(CommandExecution).where(CommandExecution.idempotency_key == key),
        )

    async def create_received(
        self,
        context: ExecutionContext,
        *,
        command_type: str,
        command_version: int,
    ) -> CommandExecution:
        execution = CommandExecution(
            idempotency_key=context.idempotency_key,
            user_id=context.user_id,
            command_type=command_type,
            command_version=command_version,
            source=context.source,
            flow_id=context.flow_id,
            graph_thread_id=context.graph_thread_id,
            correlation_id=context.correlation_id,
            status="received",
        )
        self._session.add(execution)
        await self._session.flush()
        return execution
