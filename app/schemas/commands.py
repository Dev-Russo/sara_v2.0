"""Catálogo de comandos aceitos pelo Harness.

Comandos são discriminados por ``type`` para que um agente não consiga inventar
um handler genérico ou enviar payloads sem validação.
"""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TaskStatus = Literal["active", "completed", "archived"]
TaskPriority = Literal[0, 1]
TASK_UPDATE_FIELDS = (
    "title",
    "description",
    "priority",
)


class CommandBase(BaseModel):
    command_id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)


class TaskCreatePayload(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    priority: TaskPriority = 0
    due_date: date | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("task title must not be blank")
        return normalized

    @model_validator(mode="after")
    def end_must_follow_start(self) -> "TaskCreatePayload":
        if self.start_at and self.end_at and self.end_at < self.start_at:
            raise ValueError("end_at cannot precede start_at")
        return self


class TaskListPayload(BaseModel):
    status: TaskStatus | None = "active"
    due_date_from: date | None = None
    due_date_to: date | None = None

    @model_validator(mode="after")
    def date_range_must_be_valid(self) -> "TaskListPayload":
        if self.due_date_from and self.due_date_to and self.due_date_to < self.due_date_from:
            raise ValueError("due_date_to cannot precede due_date_from")
        return self


class TaskSearchPayload(BaseModel):
    query: str = Field(min_length=1)
    status: TaskStatus | None = "active"

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("task search query must not be blank")
        return normalized


class TaskUpdateChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    priority: TaskPriority | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("task title must not be blank")
        return normalized

    @model_validator(mode="after")
    def must_contain_change(self) -> "TaskUpdateChanges":
        if not self.model_fields_set.intersection(TASK_UPDATE_FIELDS):
            raise ValueError("task update must contain at least one change")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("task title cannot be cleared")
        if "priority" in self.model_fields_set and self.priority is None:
            raise ValueError("task priority cannot be cleared")
        return self


class TaskUpdatePayload(TaskUpdateChanges):
    query: str = Field(min_length=1)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("task update query must not be blank")
        return normalized


class TaskUpdateByIdPayload(TaskUpdateChanges):
    task_id: UUID


class TaskIdPayload(BaseModel):
    task_id: UUID


class TaskCompletePayload(BaseModel):
    query: str | None = None

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class TaskIdsPayload(BaseModel):
    task_ids: list[UUID] = Field(min_length=1)


class TaskReschedulePayload(BaseModel):
    task_id: UUID
    due_date: date | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None

    @model_validator(mode="after")
    def require_target(self) -> "TaskReschedulePayload":
        if self.due_date is None and self.start_at is None and self.end_at is None:
            raise ValueError("reschedule requires a date or time")
        return self


class TaskCreateManyPayload(BaseModel):
    tasks: list[TaskCreatePayload] = Field(min_length=1)


class ReminderCreatePayload(BaseModel):
    task_id: UUID
    remind_at: datetime


class ReminderListPayload(BaseModel):
    task_id: UUID | None = None
    include_sent: bool = False


class ReminderCancelPayload(BaseModel):
    reminder_id: UUID


class TasksCreateCommand(CommandBase):
    type: Literal["tasks.create"]
    payload: TaskCreatePayload


class TasksListCommand(CommandBase):
    type: Literal["tasks.list"]
    payload: TaskListPayload = Field(default_factory=TaskListPayload)


class TasksCompleteCommand(CommandBase):
    type: Literal["tasks.complete"]
    payload: TaskCompletePayload


class TasksCompleteByIdCommand(CommandBase):
    type: Literal["tasks.complete_by_id"]
    payload: TaskIdPayload


class TasksUpdateCommand(CommandBase):
    type: Literal["tasks.update"]
    payload: TaskUpdatePayload


class TasksUpdateByIdCommand(CommandBase):
    type: Literal["tasks.update_by_id"]
    payload: TaskUpdateByIdPayload


class TasksRescheduleCommand(CommandBase):
    type: Literal["tasks.reschedule"]
    payload: TaskReschedulePayload


class TasksDeleteCommand(CommandBase):
    type: Literal["tasks.delete"]
    payload: TaskIdPayload


class TasksCreateManyCommand(CommandBase):
    type: Literal["tasks.create_many"]
    payload: TaskCreateManyPayload


class TasksCompleteManyCommand(CommandBase):
    type: Literal["tasks.complete_many"]
    payload: TaskIdsPayload


class TasksUpdateManyCommand(CommandBase):
    type: Literal["tasks.update_many"]
    payload: TaskIdsPayload


class TasksRescheduleManyCommand(CommandBase):
    type: Literal["tasks.reschedule_many"]
    payload: TaskIdsPayload


class TasksDeleteManyCommand(CommandBase):
    type: Literal["tasks.delete_many"]
    payload: TaskIdsPayload


class RemindersCreateCommand(CommandBase):
    type: Literal["reminders.create"]
    payload: ReminderCreatePayload


class RemindersListCommand(CommandBase):
    type: Literal["reminders.list"]
    payload: ReminderListPayload = Field(default_factory=ReminderListPayload)


class RemindersCancelCommand(CommandBase):
    type: Literal["reminders.cancel"]
    payload: ReminderCancelPayload


Command = Annotated[
    (
        TasksCreateCommand
        | TasksListCommand
        | TasksCompleteCommand
        | TasksCompleteByIdCommand
        | TasksUpdateCommand
        | TasksUpdateByIdCommand
        | TasksRescheduleCommand
        | TasksDeleteCommand
        | TasksCreateManyCommand
        | TasksCompleteManyCommand
        | TasksUpdateManyCommand
        | TasksRescheduleManyCommand
        | TasksDeleteManyCommand
        | RemindersCreateCommand
        | RemindersListCommand
        | RemindersCancelCommand
    ),
    Field(discriminator="type"),
]
