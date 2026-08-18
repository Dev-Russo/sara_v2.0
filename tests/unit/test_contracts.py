from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.harness.confirmation import normalize_confirmation
from app.harness.policies import requires_confirmation
from app.scheduler.idempotency import scheduled_idempotency_key
from app.schemas.commands import TaskCreatePayload, TasksCreateCommand


def test_task_create_normalizes_title() -> None:
    command = TasksCreateCommand(
        type="tasks.create",
        payload={"title": "  revisar   documentação  ", "due_date": date(2026, 8, 19)},
    )

    assert command.payload.title == "revisar documentação"


def test_blank_task_title_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TaskCreatePayload(title="   ")


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
