"""Seam do Telegram; tipos do SDK não devem entrar no domínio."""

from typing import Protocol


class TelegramGateway(Protocol):
    async def send_message(self, chat_id: str, text: str) -> None:
        """Envia uma mensagem sem expor o cliente externo aos agentes."""

