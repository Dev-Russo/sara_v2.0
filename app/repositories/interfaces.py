"""Seams de persistência; repositories não controlam commit."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.models.confirmation_request import ConfirmationRequest
from app.schemas.checkpoints import GraphCheckpointData, GraphContinuationState
from app.schemas.commands import (
    TaskCreatePayload,
    TaskListPayload,
    TaskSearchPayload,
    TaskUpdateChanges,
)
from app.schemas.tasks import TaskListResult, TaskView
from app.schemas.telegram import TelegramDeliveryData, TelegramReplyMarkup


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
    async def get_id_by_telegram_chat_id(self, chat_id: str) -> UUID | None:
        """Finds the internal user linked to an authorized private chat."""

    async def ensure_exists(self, user_id: UUID) -> None:
        """Garante o usuário autenticado sem aceitar identidade do payload."""


class ProcessedUpdateRepository(Protocol):
    async def record_if_new(
        self,
        *,
        update_id: int,
        user_id: UUID,
        telegram_chat_id: str,
        event_type: str,
        received_at: datetime,
    ) -> bool:
        """Record an update once inside the ingress transaction."""


class TelegramDeliveryRepository(Protocol):
    async def create_pending(
        self,
        *,
        update_id: int,
        user_id: UUID,
        chat_id: str,
        text: str,
        reply_markup: TelegramReplyMarkup | None,
    ) -> TelegramDeliveryData:
        """Persiste um snapshot de resposta antes da chamada externa."""

    async def get_pending_for_update(
        self,
        *,
        update_id: int,
        user_id: UUID,
    ) -> TelegramDeliveryData | None:
        """Busca uma entrega pendente dentro do escopo do usuÃ¡rio."""

    async def mark_attempt(self, *, update_id: int, user_id: UUID) -> None:
        """Registra uma tentativa antes do envio externo."""

    async def mark_failed(
        self,
        *,
        update_id: int,
        user_id: UUID,
        error_code: str,
    ) -> None:
        """MantÃ©m a entrega pendente e registra um cÃ³digo seguro de falha."""

    async def mark_delivered(self, *, update_id: int, user_id: UUID) -> None:
        """Marca a entrega somente apÃ³s o provedor confirmar sucesso."""


class GraphCheckpointRepository(Protocol):
    async def get_for_thread(
        self,
        *,
        graph_thread_id: str,
        user_id: UUID,
    ) -> GraphCheckpointData | None:
        """Carrega o último checkpoint dentro do escopo do usuário."""

    async def save(
        self,
        *,
        graph_thread_id: str,
        user_id: UUID,
        state: GraphContinuationState,
        expected_version: int | None,
    ) -> GraphCheckpointData:
        """Salva um novo snapshot sem esconder o commit da transação."""


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
