"""Repository assíncrono para o último checkpoint de cada thread."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph_checkpoint import GraphCheckpoint
from app.repositories.interfaces import GraphCheckpointRepository
from app.schemas.checkpoints import GraphCheckpointData, GraphContinuationState


class GraphCheckpointConflictError(RuntimeError):
    """Indica que outro turno atualizou o checkpoint desde a leitura."""


class GraphCheckpointOwnershipError(RuntimeError):
    """Indica tentativa de reutilizar um thread de outro usuário."""


class SqlAlchemyGraphCheckpointRepository(GraphCheckpointRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_thread(
        self,
        *,
        graph_thread_id: str,
        user_id: UUID,
    ) -> GraphCheckpointData | None:
        result = await self._session.execute(
            select(GraphCheckpoint).where(
                GraphCheckpoint.graph_thread_id == graph_thread_id,
                GraphCheckpoint.user_id == user_id,
            ),
        )
        checkpoint = result.scalar_one_or_none()
        return _to_data(checkpoint) if checkpoint is not None else None

    async def save(
        self,
        *,
        graph_thread_id: str,
        user_id: UUID,
        state: GraphContinuationState,
        expected_version: int | None,
    ) -> GraphCheckpointData:
        result = await self._session.execute(
            select(GraphCheckpoint)
            .where(GraphCheckpoint.graph_thread_id == graph_thread_id)
            .with_for_update(),
        )
        checkpoint = result.scalar_one_or_none()

        if checkpoint is None:
            if expected_version is not None:
                raise GraphCheckpointConflictError("checkpoint was created concurrently")
            checkpoint = GraphCheckpoint(
                graph_thread_id=graph_thread_id,
                user_id=user_id,
                state_payload=state.model_dump(mode="json"),
                version=1,
            )
            try:
                async with self._session.begin_nested():
                    self._session.add(checkpoint)
                    await self._session.flush()
            except IntegrityError as error:
                raise GraphCheckpointConflictError(
                    "checkpoint was created concurrently",
                ) from error
            return _to_data(checkpoint)

        if checkpoint.user_id != user_id:
            raise GraphCheckpointOwnershipError("checkpoint belongs to another user")
        if expected_version is None or checkpoint.version != expected_version:
            raise GraphCheckpointConflictError("checkpoint version is stale")

        checkpoint.state_payload = state.model_dump(mode="json")
        checkpoint.version += 1
        await self._session.flush()
        return _to_data(checkpoint)


def _to_data(checkpoint: GraphCheckpoint) -> GraphCheckpointData:
    return GraphCheckpointData(
        graph_thread_id=checkpoint.graph_thread_id,
        user_id=checkpoint.user_id,
        state=GraphContinuationState.model_validate(checkpoint.state_payload),
        version=checkpoint.version,
    )
