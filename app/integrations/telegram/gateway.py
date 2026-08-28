"""Adapter assíncrono para a API HTTP do Telegram."""

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
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": text,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        try:
            response = await self._http_client.post(
                f"{self._api_base_url}/bot{self._bot_token}/sendMessage",
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
                "telegram API rejected message",
                code="TELEGRAM_API_REJECTED",
            )
