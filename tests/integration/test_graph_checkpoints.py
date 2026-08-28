from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.graph.checkpoint import (
    GraphCheckpointConflictError,
    GraphCheckpointOwnershipError,
    PersistentGraphRunner,
)
from app.models.user import User
from app.repositories.graph_checkpoint_repository import SqlAlchemyGraphCheckpointRepository
from app.schemas.checkpoints import GraphContinuationState
from app.schemas.commands import TaskDeletePayload, TasksCreateCommand
from app.schemas.events import ConfirmationEvent, ExecutionContext, MessageEvent
from app.schemas.results import HarnessResult, ResponseDecision
from app.schemas.tasks import TaskCandidate


@dataclass
class RecordingGraph:
    calls: list[dict[str, object]] = field(default_factory=list)

    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        self.calls.append(state)
        if isinstance(state["event"], ConfirmationEvent):
            return {
                **state,
                "pending_confirmation_id": None,
                "response_decision": ResponseDecision(message="Confirmado."),
            }
        return {
            **state,
            "response_decision": ResponseDecision(message="Confirma?"),
            "agent_decision": None,
            "harness_result": HarnessResult(
                status="awaiting_confirmation",
                command_id=uuid4(),
                command_type="tasks.delete",
            ),
            "resolved_command": TasksCreateCommand(
                type="tasks.create",
                payload={"title": "transitório"},
            ),
        }


def make_context(*, user_id: UUID, thread_id: str, key: str) -> ExecutionContext:
    return ExecutionContext(
        user_id=user_id,
        graph_thread_id=thread_id,
        correlation_id=key,
        idempotency_key=key,
        source="test",
    )


async def create_user(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: UUID,
) -> None:
    async with session_factory() as session:
        session.add(User(id=user_id))
        await session.commit()


@pytest.mark.asyncio
async def test_runner_rehydrates_continuation_after_new_instance(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = uuid4()
    thread_id = f"telegram:{user_id}"
    await create_user(session_factory, user_id)
    confirmation_id = uuid4()
    first_graph = RecordingGraph()
    first_runner = PersistentGraphRunner(first_graph, session_factory)

    await first_runner.ainvoke(
        {
            "event": MessageEvent(
                event_id="telegram:1",
                user_id=user_id,
                text="excluir relatório",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(
                user_id=user_id,
                thread_id=thread_id,
                key="telegram:1",
            ),
            "active_flow": "task",
            "pending_confirmation_id": confirmation_id,
            "pending_task_candidates": [
                TaskCandidate(id=uuid4(), title="Relatório"),
            ],
            "pending_task_delete": TaskDeletePayload(query="Relatório"),
        },
    )

    continuation = await first_runner.get_continuation(
        graph_thread_id=thread_id,
        user_id=user_id,
    )
    assert continuation.pending_confirmation_id == confirmation_id

    second_graph = RecordingGraph()
    second_runner = PersistentGraphRunner(second_graph, session_factory)
    await second_runner.ainvoke(
        {
            "event": ConfirmationEvent(
                confirmation_id=confirmation_id,
                user_id=user_id,
                decision="confirm",
                received_at=datetime.now(UTC),
                source="test",
            ),
            "context": make_context(
                user_id=user_id,
                thread_id=thread_id,
                key="telegram:2",
            ),
        },
    )

    resumed_state = second_graph.calls[0]
    assert resumed_state["pending_confirmation_id"] == confirmation_id
    assert resumed_state["pending_task_delete"].query == "Relatório"
    assert resumed_state.get("response_decision") is None
    assert resumed_state.get("harness_result") is None
    assert resumed_state.get("resolved_command") is None
    assert (
        await second_runner.get_continuation(
            graph_thread_id=thread_id,
            user_id=user_id,
        )
    ).pending_confirmation_id is None


@pytest.mark.asyncio
async def test_repository_keeps_latest_version_and_enforces_ownership(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner_id = uuid4()
    other_user_id = uuid4()
    thread_id = f"telegram:{owner_id}"
    await create_user(session_factory, owner_id)
    await create_user(session_factory, other_user_id)
    first_state = GraphContinuationState(active_flow="task")
    second_state = GraphContinuationState(pending_confirmation_id=uuid4())

    async with session_factory() as session:
        async with session.begin():
            repository = SqlAlchemyGraphCheckpointRepository(session)
            first = await repository.save(
                graph_thread_id=thread_id,
                user_id=owner_id,
                state=first_state,
                expected_version=None,
            )
    assert first.version == 1

    async with session_factory() as session:
        async with session.begin():
            repository = SqlAlchemyGraphCheckpointRepository(session)
            second = await repository.save(
                graph_thread_id=thread_id,
                user_id=owner_id,
                state=second_state,
                expected_version=first.version,
            )
    assert second.version == 2

    async with session_factory() as session:
        async with session.begin():
            repository = SqlAlchemyGraphCheckpointRepository(session)
            assert await repository.get_for_thread(
                graph_thread_id=thread_id,
                user_id=other_user_id,
            ) is None
            with pytest.raises(GraphCheckpointOwnershipError):
                await repository.save(
                    graph_thread_id=thread_id,
                    user_id=other_user_id,
                    state=first_state,
                    expected_version=second.version,
                )
            with pytest.raises(GraphCheckpointConflictError):
                await repository.save(
                    graph_thread_id=thread_id,
                    user_id=owner_id,
                    state=first_state,
                    expected_version=first.version,
                )
