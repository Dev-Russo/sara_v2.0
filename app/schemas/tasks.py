"""DTOs públicos de tarefas."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TaskStatus = Literal["active", "completed", "archived"]
TaskPriority = Literal[0, 1]


class TaskView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None
    start_at: datetime | None
    end_at: datetime | None
    completed_at: datetime | None


class TaskListResult(BaseModel):
    items: list[TaskView]
    total: int


class TaskCandidate(BaseModel):
    id: UUID
    title: str
    due_date: date | None = None


class TaskCreationResult(BaseModel):
    task: TaskView
    duplicate: bool


class TaskCompletionResult(BaseModel):
    task: TaskView | None = None
    duplicate: bool = False
    error_code: str | None = None
    candidates: list[TaskCandidate] = Field(default_factory=list)
    query: str | None = None


class TaskDeletionResult(BaseModel):
    command_id: UUID | None = None
    command_type: str | None = None
    task: TaskView | None = None
    duplicate: bool = False
    awaiting_confirmation: bool = False
    confirmation_id: UUID | None = None
    error_code: str | None = None
    candidates: list[TaskCandidate] = Field(default_factory=list)
    query: str | None = None
    effect: dict[str, object] | None = None


class TaskUpdateResult(BaseModel):
    task: TaskView | None = None
    changed_fields: list[str] = Field(default_factory=list)
    duplicate: bool = False
    error_code: str | None = None
    candidates: list[TaskCandidate] = Field(default_factory=list)
    query: str | None = None
    effect: dict[str, object] | None = None
