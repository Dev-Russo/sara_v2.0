"""Estado tipado do Graph."""

from typing import TypedDict
from uuid import UUID

from app.schemas.commands import Command, TaskDeletePayload, TaskUpdatePayload
from app.schemas.decisions import AgentDecision
from app.schemas.events import ConfirmationEvent, ExecutionContext, MessageEvent
from app.schemas.results import HarnessResult, ResponseDecision
from app.schemas.tasks import TaskCandidate


class GraphState(TypedDict, total=False):
    event: MessageEvent | ConfirmationEvent
    context: ExecutionContext
    active_flow: str | None
    pending_confirmation_id: UUID | None
    agent_decision: AgentDecision | None
    harness_result: HarnessResult | None
    response_decision: ResponseDecision | None
    pending_task_candidates: list[TaskCandidate]
    pending_task_update: TaskUpdatePayload | None
    pending_task_delete: TaskDeletePayload | None
    resolved_command: Command | None
