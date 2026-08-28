"""Runner que torna durável o estado de continuação do Graph."""

from collections.abc import Mapping
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.graph.state import GraphState
from app.repositories.graph_checkpoint_repository import (
    GraphCheckpointConflictError,
    GraphCheckpointOwnershipError,
    SqlAlchemyGraphCheckpointRepository,
)
from app.schemas.checkpoints import GraphCheckpointData, GraphContinuationState
from app.schemas.events import ExecutionContext


class GraphInvoker(Protocol):
    async def ainvoke(self, state: GraphState) -> GraphState:
        """Executa um turno do Graph."""


class GraphSession(GraphInvoker, Protocol):
    async def get_continuation(
        self,
        *,
        graph_thread_id: str,
        user_id: UUID,
    ) -> GraphContinuationState:
        """Lê a continuação atual para preparar o próximo evento."""


class PersistentGraphRunner(GraphSession):
    """Carrega e salva a continuação sem persistir dados transitórios do turno."""

    def __init__(
        self,
        graph: GraphInvoker,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._graph = graph
        self._session_factory = session_factory

    def get_graph(self):
        """Expõe a topologia subjacente para relatórios sem alterar a execução."""

        get_graph = getattr(self._graph, "get_graph", None)
        if get_graph is None:
            raise AttributeError("wrapped graph does not expose its topology")
        return get_graph()

    async def get_continuation(
        self,
        *,
        graph_thread_id: str,
        user_id: UUID,
    ) -> GraphContinuationState:
        checkpoint = await self._get_checkpoint(
            graph_thread_id=graph_thread_id,
            user_id=user_id,
        )
        return checkpoint.state if checkpoint is not None else GraphContinuationState()

    async def ainvoke(self, state: GraphState) -> GraphState:
        context = state.get("context")
        if not isinstance(context, ExecutionContext):
            raise ValueError("Graph state requires an execution context")

        checkpoint = await self._get_checkpoint(
            graph_thread_id=context.graph_thread_id,
            user_id=context.user_id,
        )
        continuation = (
            checkpoint.state
            if checkpoint is not None
            else _continuation_from_state(state)
        )
        execution_state = _merge_state(state, continuation)
        result = await self._graph.ainvoke(execution_state)
        if not isinstance(result, Mapping):
            raise TypeError("Graph result must be a mapping")

        next_state = cast(GraphState, dict(result))
        await self._save_checkpoint(
            graph_thread_id=context.graph_thread_id,
            user_id=context.user_id,
            state=_continuation_from_state(next_state),
            expected_version=checkpoint.version if checkpoint is not None else None,
        )
        return next_state

    async def _get_checkpoint(
        self,
        *,
        graph_thread_id: str,
        user_id: UUID,
    ) -> GraphCheckpointData | None:
        async with self._session_factory() as session:
            async with session.begin():
                repository = SqlAlchemyGraphCheckpointRepository(session)
                return await repository.get_for_thread(
                    graph_thread_id=graph_thread_id,
                    user_id=user_id,
                )

    async def _save_checkpoint(
        self,
        *,
        graph_thread_id: str,
        user_id: UUID,
        state: GraphContinuationState,
        expected_version: int | None,
    ) -> GraphCheckpointData:
        async with self._session_factory() as session:
            async with session.begin():
                repository = SqlAlchemyGraphCheckpointRepository(session)
                return await repository.save(
                    graph_thread_id=graph_thread_id,
                    user_id=user_id,
                    state=state,
                    expected_version=expected_version,
                )


def _continuation_from_state(state: Mapping[str, object]) -> GraphContinuationState:
    return GraphContinuationState.model_validate(
        {
            "active_flow": state.get("active_flow"),
            "pending_confirmation_id": state.get("pending_confirmation_id"),
            "pending_task_candidates": state.get("pending_task_candidates", []),
            "pending_task_update": state.get("pending_task_update"),
            "pending_task_delete": state.get("pending_task_delete"),
        },
    )


def _merge_state(
    state: GraphState,
    continuation: GraphContinuationState,
) -> GraphState:
    return {
        "event": state["event"],
        "context": state["context"],
        "active_flow": continuation.active_flow,
        "pending_confirmation_id": continuation.pending_confirmation_id,
        "pending_task_candidates": continuation.pending_task_candidates,
        "pending_task_update": continuation.pending_task_update,
        "pending_task_delete": continuation.pending_task_delete,
        "agent_decision": None,
        "harness_result": None,
        "response_decision": None,
        "resolved_command": None,
    }


__all__ = [
    "GraphInvoker",
    "GraphSession",
    "GraphCheckpointConflictError",
    "GraphCheckpointOwnershipError",
    "PersistentGraphRunner",
]
