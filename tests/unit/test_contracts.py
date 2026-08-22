from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.harness.confirmation import normalize_confirmation
from app.harness.handlers import TaskConfirmationResolver
from app.harness.policies import requires_confirmation
from app.scheduler.idempotency import scheduled_idempotency_key
from app.schemas.commands import (
    TaskCreatePayload,
    TaskDeletePayload,
    TasksCreateCommand,
    TasksDeleteByIdCommand,
    TasksDeleteCommand,
    TasksListCommand,
    TasksUpdateByIdCommand,
    TasksUpdateCommand,
    TaskUpdateByIdPayload,
    TaskUpdatePayload,
)


def test_task_create_normalizes_title() -> None:
    command = TasksCreateCommand(
        type="tasks.create",
        payload={"title": "  revisar   documentação  ", "due_date": date(2026, 8, 19)},
    )

    assert command.payload.title == "Revisar documentação"
    assert command.payload.priority == 0


def test_task_payload_capitalizes_title_and_description() -> None:
    payload = TaskCreatePayload(
        title="  comprar feij\u00e3o  ",
        description="  ler   livro  ",
    )

    assert payload.title == "Comprar feij\u00e3o"
    assert payload.description == "Ler livro"


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
        query="  revisar   documento  ",
        title="  revisar   documento final  ",
    )

    assert payload.title == "Revisar documento final"
    assert payload.query == "revisar documento"


def test_task_update_capitalizes_title_and_description() -> None:
    payload = TaskUpdatePayload(
        query="tarefa 2",
        title="tarefa 2",
        description="comprar caf\u00e9",
    )

    assert payload.title == "Tarefa 2"
    assert payload.description == "Comprar caf\u00e9"


def test_task_update_requires_a_field_and_allows_clearing_nullable_fields() -> None:
    clear_description = TaskUpdatePayload(query="documento", description=None)

    assert "description" in clear_description.model_fields_set
    assert clear_description.description is None

    with pytest.raises(ValidationError):
        TaskUpdatePayload(query="documento")

    with pytest.raises(ValidationError):
        TaskUpdatePayload(query="documento", title=None)

    with pytest.raises(ValidationError):
        TaskUpdatePayload(query="documento", due_date=date(2026, 8, 20))

    with pytest.raises(ValidationError):
        TaskUpdatePayload(query="documento", priority=1, due_date=date(2026, 8, 20))

    with pytest.raises(ValidationError):
        TaskUpdatePayload(query="documento", priority=None)


def test_task_update_by_id_reuses_update_change_contract() -> None:
    command = TasksUpdateByIdCommand(
        type="tasks.update_by_id",
        payload={"task_id": uuid4(), "description": None, "priority": 1},
    )

    assert isinstance(command.payload, TaskUpdateByIdPayload)
    assert command.payload.model_fields_set == {"task_id", "description", "priority"}


def test_task_update_command_uses_textual_reference() -> None:
    command = TasksUpdateCommand(
        type="tasks.update",
        payload={"query": "estudar arquitetura", "title": "Estudar sistemas"},
    )

    assert command.payload.query == "estudar arquitetura"


def test_task_list_defaults_to_active_and_allows_explicit_all() -> None:
    default_command = TasksListCommand(type="tasks.list")
    all_command = TasksListCommand(type="tasks.list", payload={"status": None})

    assert default_command.payload.status == "active"
    assert all_command.payload.status is None


def test_confirmation_policy_covers_destructive_operations() -> None:
    assert requires_confirmation("tasks.delete")
    assert requires_confirmation("tasks.delete_by_id")
    assert requires_confirmation("tasks.update_many")
    assert not requires_confirmation("tasks.update")


def test_task_delete_command_uses_textual_reference() -> None:
    command = TasksDeleteCommand(
        type="tasks.delete",
        payload={"query": "  apagar relatório  "},
    )

    assert isinstance(command.payload, TaskDeletePayload)
    assert command.payload.query == "apagar relatório"


def test_task_delete_by_id_is_an_internal_command() -> None:
    command = TasksDeleteByIdCommand(
        type="tasks.delete_by_id",
        payload={"task_id": uuid4()},
    )

    assert command.payload.task_id is not None


def test_task_confirmation_resolver_exposes_harness_seam() -> None:
    assert hasattr(TaskConfirmationResolver, "resolve")


def test_confirmation_text_is_strictly_normalized() -> None:
    assert normalize_confirmation("  CONFIRMAR ") == "confirm"
    assert normalize_confirmation("não") == "cancel"
    assert normalize_confirmation("talvez") is None


def test_scheduler_key_is_stable() -> None:
    resource = str(uuid4())
    key = scheduled_idempotency_key(resource, "2026-08-19T10:00")

    assert key == scheduled_idempotency_key(resource, "2026-08-19T10:00")
    assert key != scheduled_idempotency_key(resource, "2026-08-19T11:00")
