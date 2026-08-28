"""Contratos para persistir somente o estado necessário à retomada do Graph."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.commands import TaskDeletePayload, TaskUpdatePayload
from app.schemas.tasks import TaskCandidate


class GraphContinuationState(BaseModel):
    """Estado durável usado para continuar o próximo turno de uma conversa."""

    model_config = ConfigDict(extra="forbid")

    active_flow: str | None = None
    pending_confirmation_id: UUID | None = None
    pending_task_candidates: list[TaskCandidate] = Field(default_factory=list)
    pending_task_update: TaskUpdatePayload | None = None
    pending_task_delete: TaskDeletePayload | None = None


class GraphCheckpointData(BaseModel):
    """Snapshot mais recente de um thread pertencente a um usuário."""

    graph_thread_id: str = Field(min_length=1, max_length=200)
    user_id: UUID
    state: GraphContinuationState
    version: int = Field(ge=1)
