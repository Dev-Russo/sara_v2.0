"""Estado tipado do Graph."""

from typing import TypedDict

from app.schemas.decisions import AgentDecision
from app.schemas.events import ExecutionContext, MessageEvent
from app.schemas.results import HarnessResult, ResponseDecision


class GraphState(TypedDict, total=False):
    event: MessageEvent
    context: ExecutionContext
    active_flow: str | None
    pending_confirmation_id: str | None
    agent_decision: AgentDecision | None
    harness_result: HarnessResult | None
    response_decision: ResponseDecision | None
