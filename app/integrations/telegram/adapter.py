"""Seam do Telegram; tipos do SDK não devem entrar no domínio."""

from typing import Protocol

from app.schemas.telegram import TelegramReplyMarkup


class TelegramDeliveryError(RuntimeError):
    """Falha controlada ao entregar uma mensagem pelo Telegram."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class TelegramGateway(Protocol):
    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: TelegramReplyMarkup | None = None,
    ) -> None:
        """Envia uma mensagem sem expor o cliente externo aos agentes."""

    async def answer_callback_query(self, callback_query_id: str) -> None:
        """Encerra o estado de carregamento de um callback no Telegram."""
