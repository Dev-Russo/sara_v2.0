"""Adapter Anthropic; a resposta deve ser validada antes de chegar ao Graph."""

from anthropic import AsyncAnthropic

from app.integrations.llm.interface import LLMClient


class AnthropicAdapter(LLMClient):
    def __init__(self, *, api_key: str, model: str, max_tokens: int = 512) -> None:
        if not api_key:
            raise ValueError("LLM API key is required")
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        text_blocks = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        if not text_blocks:
            raise RuntimeError("LLM returned no text content")
        return "\n".join(text_blocks)
