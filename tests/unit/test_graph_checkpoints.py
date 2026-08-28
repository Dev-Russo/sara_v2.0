from uuid import uuid4

from app.schemas.checkpoints import GraphContinuationState
from app.schemas.commands import TaskDeletePayload
from app.schemas.tasks import TaskCandidate


def test_graph_continuation_state_round_trips_through_json() -> None:
    confirmation_id = uuid4()
    state = GraphContinuationState(
        active_flow="task",
        pending_confirmation_id=confirmation_id,
        pending_task_candidates=[
            TaskCandidate(
                id=uuid4(),
                title="Revisar documentação",
            ),
        ],
        pending_task_delete=TaskDeletePayload(query="Revisar documentação"),
    )

    payload = state.model_dump(mode="json")

    assert GraphContinuationState.model_validate(payload) == state
