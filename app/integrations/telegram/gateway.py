"""Adapter assíncrono para a API HTTP do Telegram."""

import html
import re

import httpx

from app.integrations.telegram.adapter import TelegramDeliveryError, TelegramGateway
from app.schemas.telegram import TelegramReplyMarkup


class HttpxTelegramGateway(TelegramGateway):
    """Implementa ``sendMessage`` sem deixar detalhes HTTP vazarem ao Graph."""

    def __init__(
        self,
        *,
        bot_token: str,
        http_client: httpx.AsyncClient,
        api_base_url: str = "https://api.telegram.org",
    ) -> None:
        self._bot_token = bot_token
        self._http_client = http_client
        self._api_base_url = api_base_url.rstrip("/")

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: TelegramReplyMarkup | None = None,
    ) -> None:
        rendered_text, parse_mode = _render_telegram_text(text)
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": rendered_text,
        }
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        await self._call_api(
            method="sendMessage",
            payload=payload,
            rejection_message="telegram API rejected message",
            rejection_code="TELEGRAM_API_REJECTED",
        )

    async def answer_callback_query(self, callback_query_id: str) -> None:
        await self._call_api(
            method="answerCallbackQuery",
            payload={"callback_query_id": callback_query_id},
            rejection_message="telegram API rejected callback",
            rejection_code="TELEGRAM_CALLBACK_REJECTED",
        )

    async def _call_api(
        self,
        *,
        method: str,
        payload: dict[str, object],
        rejection_message: str,
        rejection_code: str,
    ) -> None:
        """Executa uma chamada Telegram e converte sua resposta em erro seguro."""

        try:
            response = await self._http_client.post(
                f"{self._api_base_url}/bot{self._bot_token}/{method}",
                json=payload,
            )
        except httpx.HTTPError as error:
            raise TelegramDeliveryError(
                "telegram API request failed",
                code="TELEGRAM_API_REQUEST_FAILED",
            ) from error

        if response.is_error:
            raise TelegramDeliveryError(
                "telegram API request failed",
                code="TELEGRAM_API_REQUEST_FAILED",
            )

        try:
            body = response.json()
        except ValueError as error:
            raise TelegramDeliveryError(
                "telegram API returned an invalid response",
                code="TELEGRAM_API_INVALID_RESPONSE",
            ) from error

        if not isinstance(body, dict) or body.get("ok") is not True:
            raise TelegramDeliveryError(
                rejection_message,
                code=rejection_code,
            )


_BOLD_MARKDOWN_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def _render_telegram_text(text: str) -> tuple[str, str | None]:
    """Converte o subconjunto de Markdown produzido pela SARA para HTML seguro."""

    if not _BOLD_MARKDOWN_RE.search(text):
        return text, None

    rendered: list[str] = []
    cursor = 0
    for match in _BOLD_MARKDOWN_RE.finditer(text):
        rendered.append(html.escape(text[cursor : match.start()]))
        rendered.append(f"<b>{html.escape(match.group(1))}</b>")
        cursor = match.end()
    rendered.append(html.escape(text[cursor:]))
    return "".join(rendered), "HTML"
