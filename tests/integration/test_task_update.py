from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.harness.handlers import register_task_handlers
from app.harness.registry import CommandRegistry
from app.harness.service import Harness
from app.schemas.commands import (
    TaskCreatePayload,
    TasksUpdateCommand,
    TaskUpdateByIdPayload,
    TaskUpdatePayload,
)
from app.schemas.events import ExecutionContext
from app.services.tasks import TaskService


def make_context(*, user_id: UUID, idempotency_key: str) -> ExecutionContext:
    return ExecutionContext(
        user_id=user_id,
        graph_thread_id="task-update-thread",
        correlation_id=idempotency_key,
        idempotency_key=idempotency_key,
        source="test",
    )


@pytest.mark.asyncio
async def test_task_service_updates_task_and_reports_changed_fields(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    await service.create_task(
        make_context(user_id=user_id, idempotency_key="update-create"),
        TaskCreatePayload(
            title="Revisar documento",
            description="Versão antiga",
            priority=0,
            due_date=date(2026, 8, 19),
        ),
    )

    result = await service.update_task(
        make_context(user_id=user_id, idempotency_key="update-task"),
        TaskUpdatePayload(
            query="Revisar documento",
            title="Revisar documento final",
            description="Versão atualizada",
            priority=1,
        ),
    )

    assert result.error_code is None
    assert result.duplicate is False
    assert result.task is not None
    assert result.task.title == "Revisar documento final"
    assert result.task.description == "Versão atualizada"
    assert result.task.priority == 1
    assert result.task.due_date == date(2026, 8, 19)
    assert result.changed_fields == ["title", "description", "priority"]


@pytest.mark.asyncio
async def test_task_service_updates_single_active_task_resolved_by_query(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    created = await service.create_task(
        make_context(user_id=user_id, idempotency_key="query-update-create"),
        TaskCreatePayload(title="Estudar arquitetura", description="Ler o capítulo 1"),
    )

    result = await service.update_task(
        make_context(user_id=user_id, idempotency_key="query-update-command"),
        TaskUpdatePayload(query="estudar arquitetura", priority=1),
    )

    assert result.task is not None
    assert result.task.id == created.task.id
    assert result.task.priority == 1
    assert result.query == "estudar arquitetura"
    assert result.changed_fields == ["priority"]


@pytest.mark.asyncio
async def test_harness_executes_tasks_update_and_returns_effect(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    harness = Harness(registry)
    user_id = uuid4()
    created = await service.create_task(
        make_context(user_id=user_id, idempotency_key="harness-update-create"),
        TaskCreatePayload(title="Revisar documento"),
    )

    result = await harness.handle(
        TasksUpdateCommand(
            type="tasks.update",
            payload={
                "query": "Revisar documento",
                "title": "Revisar documento final",
                "priority": 1,
            },
        ),
        make_context(user_id=user_id, idempotency_key="harness-update-command"),
    )

    assert result.status == "executed"
    assert result.command_type == "tasks.update"
    assert result.effect == {
        "kind": "task_updated",
        "task_id": str(created.task.id),
        "title": "Revisar documento final",
        "changed_fields": ["title", "priority"],
        "resolution": {"query": "Revisar documento", "candidate_count": 1},
    }


@pytest.mark.asyncio
async def test_task_update_is_idempotent_and_does_not_reapply_changes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    await service.create_task(
        make_context(user_id=user_id, idempotency_key="idempotent-update-create"),
        TaskCreatePayload(title="Título inicial"),
    )
    context = make_context(user_id=user_id, idempotency_key="idempotent-update-command")

    first = await service.update_task(
        context,
        TaskUpdatePayload(query="Título inicial", title="Título atualizado"),
    )
    second = await service.update_task(
        context,
        TaskUpdatePayload(query="Título inicial", title="Outro título"),
    )

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.task is not None
    assert second.task.title == "Título atualizado"
    assert second.changed_fields == ["title"]


@pytest.mark.asyncio
async def test_harness_update_duplicate_returns_original_effect(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    harness = Harness(registry)
    user_id = uuid4()
    await service.create_task(
        make_context(user_id=user_id, idempotency_key="original-effect-create"),
        TaskCreatePayload(title="Título inicial"),
    )

    first = await harness.handle(
        TasksUpdateCommand(
            type="tasks.update",
            payload={"query": "Título inicial", "title": "Primeira alteração"},
        ),
        make_context(user_id=user_id, idempotency_key="original-effect-command"),
    )
    await harness.handle(
        TasksUpdateCommand(
            type="tasks.update",
            payload={"query": "Título inicial", "title": "Segunda alteração"},
        ),
        make_context(user_id=user_id, idempotency_key="second-effect-command"),
    )
    duplicate = await harness.handle(
        TasksUpdateCommand(
            type="tasks.update",
            payload={"query": "Título inicial", "title": "Ignorar esta alteração"},
        ),
        make_context(user_id=user_id, idempotency_key="original-effect-command"),
    )

    assert first.effect is not None
    assert duplicate.status == "duplicate"
    assert duplicate.effect == first.effect


@pytest.mark.asyncio
async def test_task_update_reports_noop_without_claiming_a_changed_field(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    await service.create_task(
        make_context(user_id=user_id, idempotency_key="noop-update-create"),
        TaskCreatePayload(title="Sem alteração"),
    )

    result = await service.update_task(
        make_context(user_id=user_id, idempotency_key="noop-update-command"),
        TaskUpdatePayload(query="Sem alteração", title="Sem alteração"),
    )

    assert result.changed_fields == []
    assert result.effect is not None
    assert result.effect["kind"] == "task_unchanged"


@pytest.mark.asyncio
async def test_task_update_rejects_task_owned_by_another_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    owner_id = uuid4()
    other_user_id = uuid4()
    await service.create_task(
        make_context(user_id=owner_id, idempotency_key="ownership-update-create"),
        TaskCreatePayload(title="Não alterar"),
    )

    result = await service.update_task(
        make_context(user_id=other_user_id, idempotency_key="ownership-update-command"),
        TaskUpdatePayload(query="Não alterar", title="Alteração indevida"),
    )

    assert result.task is None
    assert result.error_code == "TASK_REFERENCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_task_update_by_id_updates_after_uuid_is_resolved(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    user_id = uuid4()
    created = await service.create_task(
        make_context(user_id=user_id, idempotency_key="by-id-update-create"),
        TaskCreatePayload(title="Reunião"),
    )

    result = await service.update_task_by_id(
        make_context(user_id=user_id, idempotency_key="by-id-update-command"),
        TaskUpdateByIdPayload(
            task_id=created.task.id,
            title="Reunião com cliente",
        ),
    )

    assert result.task is not None
    assert result.task.title == "Reunião com cliente"
    assert result.changed_fields == ["title"]


@pytest.mark.asyncio
async def test_harness_update_reports_ambiguous_reference_without_mutating_tasks(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TaskService(session_factory)
    registry = CommandRegistry()
    register_task_handlers(registry, service)
    harness = Harness(registry)
    user_id = uuid4()
    await service.create_task(
        make_context(user_id=user_id, idempotency_key="ambiguous-update-first"),
        TaskCreatePayload(title="Ler livro de manhã"),
    )
    await service.create_task(
        make_context(user_id=user_id, idempotency_key="ambiguous-update-second"),
        TaskCreatePayload(title="Ler livro à noite"),
    )

    result = await harness.handle(
        TasksUpdateCommand(
            type="tasks.update",
            payload={"query": "ler livro", "priority": 1},
        ),
        make_context(user_id=user_id, idempotency_key="ambiguous-update-command"),
    )

    assert result.status == "awaiting_selection"
    assert result.effect["kind"] == "task_update_ambiguous"
    assert result.effect["total"] == 2
