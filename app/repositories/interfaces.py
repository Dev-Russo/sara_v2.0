"""Seams de persistência; repositories não controlam commit."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.models.confirmation_request import ConfirmationRequest
from app.schemas.commands import (
    TaskCreatePayload,
    TaskListPayload,
    TaskSearchPayload,
    TaskUpdateChanges,
)
from app.schemas.tasks import TaskListResult, TaskView


class TaskRepository(Protocol):
    async def create(self, user_id: UUID, payload: TaskCreatePayload) -> TaskView:
        """Cria uma tarefa dentro da transação controlada pelo service."""

    async def get_for_user(self, user_id: UUID, task_id: UUID) -> TaskView | None:
        """Busca uma tarefa sempre dentro do escopo do usuário."""

    async def complete_for_user(self, user_id: UUID, task_id: UUID) -> TaskView | None:
        """Conclui uma tarefa ativa dentro do escopo do usuário."""

    async def update_for_user(
        self,
        user_id: UUID,
        task_id: UUID,
        payload: TaskUpdateChanges,
    ) -> TaskView | None:
        """Atualiza uma tarefa pertencente ao usuário dentro da transação."""

    async def search_for_user(
        self,
        user_id: UUID,
        payload: TaskSearchPayload,
    ) -> TaskListResult:
        """Busca candidatos textuais dentro do escopo de tarefas ativas."""

    async def list_for_user(
        self,
        user_id: UUID,
        payload: TaskListPayload,
    ) -> TaskListResult:
        """Lista tarefas sem expor detalhes da persistência ao service."""

    async def delete_for_user(self, user_id: UUID, task_id: UUID) -> TaskView | None:
        """Remove uma tarefa ativa pertencente ao usuário."""


class UserRepository(Protocol):
    async def ensure_exists(self, user_id: UUID) -> None:
        """Garante o usuário autenticado sem aceitar identidade do payload."""


class ConfirmationRepository(Protocol):
    async def create_pending(
        self,
        *,
        user_id: UUID,
        execution_id: UUID,
        command_id: UUID,
        command_type: str,
        payload_snapshot: dict[str, object],
        summary: str,
        expires_at: datetime,
    ) -> ConfirmationRequest:
        """Cria uma confirmação dentro da transação do service."""

    async def get_for_user(
        self,
        user_id: UUID,
        confirmation_id: UUID,
    ) -> ConfirmationRequest | None:
        """Carrega uma confirmação pertencente ao usuário."""

    async def transition_pending(
        self,
        *,
        user_id: UUID,
        confirmation_id: UUID,
        status: str,
        resolved_at: datetime,
    ) -> bool:
        """Consome ou cancela uma pendência no máximo uma vez."""
