"""Adapter Anthropic; a resposta deve ser validada antes de chegar ao Graph."""

from app.integrations.llm.interface import LLMClient


class AnthropicAdapter(LLMClient):
    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        raise NotImplementedError("Anthropic adapter is not implemented yet")

