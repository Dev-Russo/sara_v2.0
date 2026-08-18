"""DTOs públicos de tarefas."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

TaskStatus = Literal["active", "completed", "archived"]
TaskPriority = Literal["normal", "important"]


class TaskView(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None
    start_at: datetime | None
    end_at: datetime | None


class TaskListResult(BaseModel):
    items: list[TaskView]
    total: int

