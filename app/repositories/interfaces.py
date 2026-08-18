"""Seams de persistência; repositories não controlam commit."""

from typing import Protocol
from uuid import UUID

from app.schemas.tasks import TaskListResult, TaskView


class TaskRepository(Protocol):
    async def get_for_user(self, user_id: UUID, task_id: UUID) -> TaskView | None:
        """Busca uma tarefa sempre dentro do escopo do usuário."""

    async def list_for_user(self, user_id: UUID) -> TaskListResult:
        """Lista tarefas sem expor detalhes da persistência ao service."""


class ConfirmationRepository(Protocol):
    async def get_pending(self, user_id: UUID, confirmation_id: UUID) -> object | None:
        """Carrega uma confirmação pertencente ao usuário."""

