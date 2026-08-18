"""Seam mínima do provedor de LLM."""

from typing import Protocol


class LLMClient(Protocol):
    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        """Retorna texto para validação pelo schema do agente."""

