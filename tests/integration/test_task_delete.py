from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.harness.handlers import build_task_confirmation_resolver, register_task_handlers
from app.harness.registry import CommandRegistry
from app.harness.service import Harness
from app.schemas.commands import TaskCreatePayload, TaskListPayload, TasksDeleteCommand
from app.schemas.events import ExecutionContext
from app.services.tasks import TaskService


def make_context(*, user_id: UUID, idempotency_key: str) -> ExecutionContext:
    return ExecutionContext(
        user_id=user_id,
        graph_thread_id="task-delete-thread",
        correlation_id=idempotency_key,
        idempotency_key=idempotency_key,
        source="test",
    )


def make_harness(service: TaskService) -> Harness:
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    return Harness(
        registry,
        confirmation_resolver=build_task_confirmation_resolver(service),
    )


@pytest.mark.asyncio
async def test_delete_requires_confirmation_and_keeps_task_until_confirmed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(
        session_factory,
        clock=lambda: datetime(2026, 8, 21, 12, tzinfo=UTC),
    )
    harness = make_harness(service)
    user_id = uuid4()
    created = await service.create_task(
        make_context(user_id=user_id, idempotency_key="delete-create"),
        TaskCreatePayload(title="Excluir depois da confirmação"),
    )

    pending = await harness.handle(
        TasksDeleteCommand(
            type="tasks.delete",
            payload={"query": "Excluir depois da confirmação"},
        ),
        make_context(user_id=user_id, idempotency_key="delete-request"),
    )

    assert pending.status == "awaiting_confirmation"
    assert pending.confirmation_id is not None
    assert pending.effect == {
        "kind": "task_delete_pending",
        "task_id": str(created.task.id),
        "title": "Excluir depois da confirmação",
        "confirmation_id": str(pending.confirmation_id),
        "summary": (
            'Excluir a tarefa "Excluir depois da confirmação"? '
            "Essa ação não poderá ser desfeita."
        ),
        "expires_at": "2026-08-21T12:10:00+00:00",
        "irreversible": True,
    }
    still_pending = await service.list_tasks(
        make_context(user_id=user_id, idempotency_key="delete-before-confirm-list"),
        TaskListPayload(status="active"),
    )
    assert [task.id for task in still_pending.items] == [created.task.id]

    result = await harness.resolve_confirmation(
        pending.confirmation_id,
        make_context(user_id=user_id, idempotency_key="delete-confirm"),
        "confirm",
    )

    assert result.status == "executed"
    assert result.effect == {
        "kind": "task_deleted",
        "task_id": str(created.task.id),
        "title": "Excluir depois da confirmação",
    }
    duplicate = await harness.resolve_confirmation(
        pending.confirmation_id,
        make_context(user_id=user_id, idempotency_key="delete-confirm-duplicate"),
        "confirm",
    )
    assert duplicate.status == "duplicate"
    assert duplicate.effect == result.effect


@pytest.mark.asyncio
async def test_delete_cancel_does_not_mutate_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    harness = make_harness(service)
    user_id = uuid4()
    created = await service.create_task(
        make_context(user_id=user_id, idempotency_key="cancel-create"),
        TaskCreatePayload(title="Não apagar"),
    )

    pending = await harness.handle(
        TasksDeleteCommand(type="tasks.delete", payload={"query": "Não apagar"}),
        make_context(user_id=user_id, idempotency_key="cancel-request"),
    )
    result = await harness.resolve_confirmation(
        pending.confirmation_id,
        make_context(user_id=user_id, idempotency_key="cancel-confirm"),
        "cancel",
    )

    assert result.status == "rejected"
    assert result.error_code == "CONFIRMATION_CANCELLED"
    remaining = await service.list_tasks(
        make_context(user_id=user_id, idempotency_key="cancel-list"),
        TaskListPayload(status="active"),
    )
    assert [task.id for task in remaining.items] == [created.task.id]


@pytest.mark.asyncio
async def test_delete_is_idempotent_while_confirmation_is_pending(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    harness = make_harness(service)
    user_id = uuid4()
    await service.create_task(
        make_context(user_id=user_id, idempotency_key="duplicate-create"),
        TaskCreatePayload(title="Solicitar exclusão uma vez"),
    )
    command = TasksDeleteCommand(
        type="tasks.delete",
        payload={"query": "Solicitar exclusão uma vez"},
    )
    context = make_context(user_id=user_id, idempotency_key="duplicate-request")

    first = await harness.handle(command, context)
    second = await harness.handle(
        command.model_copy(update={"command_id": uuid4()}),
        context,
    )

    assert first.status == "awaiting_confirmation"
    assert second.status == "awaiting_confirmation"
    assert second.confirmation_id == first.confirmation_id


@pytest.mark.asyncio
async def test_delete_does_not_select_completed_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    harness = make_harness(service)
    user_id = uuid4()
    created = await service.create_task(
        make_context(user_id=user_id, idempotency_key="completed-delete-create"),
        TaskCreatePayload(title="Tarefa concluída"),
    )
    await service.complete_task_by_id(
        make_context(user_id=user_id, idempotency_key="completed-delete-complete"),
        created.task.id,
    )

    result = await harness.handle(
        TasksDeleteCommand(type="tasks.delete", payload={"query": "Tarefa concluída"}),
        make_context(user_id=user_id, idempotency_key="completed-delete-request"),
    )

    assert result.status == "failed"
    assert result.error_code == "TASK_REFERENCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_expired_delete_confirmation_does_not_mutate_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    current_time = [datetime(2026, 8, 21, 12, tzinfo=UTC)]
    service = TaskService(session_factory, clock=lambda: current_time[0])
    harness = make_harness(service)
    user_id = uuid4()
    created = await service.create_task(
        make_context(user_id=user_id, idempotency_key="expired-create"),
        TaskCreatePayload(title="Confirmação expirada"),
    )

    pending = await harness.handle(
        TasksDeleteCommand(
            type="tasks.delete",
            payload={"query": "Confirmação expirada"},
        ),
        make_context(user_id=user_id, idempotency_key="expired-request"),
    )
    current_time[0] += timedelta(minutes=11)
    result = await harness.resolve_confirmation(
        pending.confirmation_id,
        make_context(user_id=user_id, idempotency_key="expired-confirm"),
        "confirm",
    )

    assert result.status == "failed"
    assert result.error_code == "CONFIRMATION_EXPIRED"
    remaining = await service.list_tasks(
        make_context(user_id=user_id, idempotency_key="expired-list"),
        TaskListPayload(status="active"),
    )
    assert [task.id for task in remaining.items] == [created.task.id]


@pytest.mark.asyncio
async def test_confirmation_from_another_user_cannot_delete_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    harness = make_harness(service)
    owner_id = uuid4()
    other_user_id = uuid4()
    await service.create_task(
        make_context(user_id=owner_id, idempotency_key="ownership-delete-create"),
        TaskCreatePayload(title="Protegida"),
    )
    pending = await harness.handle(
        TasksDeleteCommand(type="tasks.delete", payload={"query": "Protegida"}),
        make_context(user_id=owner_id, idempotency_key="ownership-delete-request"),
    )

    result = await harness.resolve_confirmation(
        pending.confirmation_id,
        make_context(user_id=other_user_id, idempotency_key="ownership-delete-confirm"),
        "confirm",
    )

    assert result.status == "failed"
    assert result.error_code == "CONFIRMATION_NOT_FOUND"
