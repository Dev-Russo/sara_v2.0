from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.harness.confirmation import normalize_confirmation
from app.harness.policies import requires_confirmation
from app.scheduler.idempotency import scheduled_idempotency_key
from app.schemas.commands import (
    TaskCreatePayload,
    TasksCreateCommand,
    TasksListCommand,
    TaskUpdatePayload,
)


def test_task_create_normalizes_title() -> None:
    command = TasksCreateCommand(
        type="tasks.create",
        payload={"title": "  revisar   documentação  ", "due_date": date(2026, 8, 19)},
    )

    assert command.payload.title == "revisar documentação"
    assert command.payload.priority == 0


def test_task_priority_accepts_only_binary_values() -> None:
    assert TasksCreateCommand(
        type="tasks.create",
        payload={"title": "tarefa prioritária", "priority": 1},
    ).payload.priority == 1

    with pytest.raises(ValidationError):
        TasksCreateCommand(
            type="tasks.create",
            payload={"title": "tarefa inválida", "priority": 2},
        )

    with pytest.raises(ValidationError):
        TasksCreateCommand(
            type="tasks.create",
            payload={"title": "tarefa legada", "priority": "normal"},
        )


def test_blank_task_title_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TaskCreatePayload(title="   ")


def test_task_update_normalizes_title() -> None:
    payload = TaskUpdatePayload(
        task_id=uuid4(),
        title="  revisar   documento final  ",
    )

    assert payload.title == "revisar documento final"


def test_task_update_requires_a_field_and_allows_clearing_nullable_fields() -> None:
    clear_description = TaskUpdatePayload(task_id=uuid4(), description=None)

    assert "description" in clear_description.model_fields_set
    assert clear_description.description is None

    with pytest.raises(ValidationError):
        TaskUpdatePayload(task_id=uuid4())

    with pytest.raises(ValidationError):
        TaskUpdatePayload(task_id=uuid4(), title=None)


def test_task_list_defaults_to_active_and_allows_explicit_all() -> None:
    default_command = TasksListCommand(type="tasks.list")
    all_command = TasksListCommand(type="tasks.list", payload={"status": None})

    assert default_command.payload.status == "active"
    assert all_command.payload.status is None


def test_confirmation_policy_covers_destructive_operations() -> None:
    assert requires_confirmation("tasks.delete")
    assert requires_confirmation("tasks.update_many")
    assert not requires_confirmation("tasks.update")


def test_confirmation_text_is_strictly_normalized() -> None:
    assert normalize_confirmation("  CONFIRMAR ") == "confirm"
    assert normalize_confirmation("não") == "cancel"
    assert normalize_confirmation("talvez") is None


def test_scheduler_key_is_stable() -> None:
    resource = str(uuid4())
    key = scheduled_idempotency_key(resource, "2026-08-19T10:00")

    assert key == scheduled_idempotency_key(resource, "2026-08-19T10:00")
    assert key != scheduled_idempotency_key(resource, "2026-08-19T11:00")
