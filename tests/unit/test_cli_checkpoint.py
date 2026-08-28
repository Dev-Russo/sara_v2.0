from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.cli import CliSession
from app.graph.state import GraphState
from app.schemas.checkpoints import GraphContinuationState
from app.schemas.events import ConfirmationEvent, ExecutionContext
from app.schemas.results import ResponseDecision


@dataclass
class RecordingGraphSession:
    continuation: GraphContinuationState
    calls: list[GraphState] = field(default_factory=list)

    async def get_continuation(
        self,
        *,
        graph_thread_id: str,
        user_id: UUID,
    ) -> GraphContinuationState:
        del graph_thread_id, user_id
        return self.continuation

    async def ainvoke(self, state: GraphState) -> GraphState:
        self.calls.append(state)
        return {
            **state,
            "pending_confirmation_id": None,
            "response_decision": ResponseDecision(message="Cancelado."),
        }


async def test_cli_uses_persisted_confirmation_when_creating_next_event() -> None:
    user_id = uuid4()
    confirmation_id = uuid4()
    graph = RecordingGraphSession(
        continuation=GraphContinuationState(
            active_flow="task",
            pending_confirmation_id=confirmation_id,
        ),
    )
    session = CliSession(
        graph=graph,
        user_id=user_id,
        graph_thread_id=f"cli:{user_id}",
    )

    response = await session.process("sim")

    assert response == "Cancelado."
    assert isinstance(graph.calls[0]["event"], ConfirmationEvent)
    assert graph.calls[0]["event"].confirmation_id == confirmation_id
    assert graph.calls[0]["context"] == ExecutionContext(
        user_id=user_id,
        graph_thread_id=f"cli:{user_id}",
        correlation_id=graph.calls[0]["context"].correlation_id,
        idempotency_key=graph.calls[0]["context"].idempotency_key,
        source="cli",
    )
