import json

import httpx
import pytest

from app.integrations.telegram.gateway import (
    HttpxTelegramGateway,
    TelegramDeliveryError,
)
from app.schemas.telegram import TelegramReplyMarkup


@pytest.mark.asyncio
async def test_gateway_sends_text_and_inline_keyboard_to_telegram() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://telegram.test",
    )
    markup = TelegramReplyMarkup(
        inline_keyboard=[
            [
                {"text": "Confirmar", "callback_data": "confirmation:confirm:id"},
                {"text": "Cancelar", "callback_data": "confirmation:cancel:id"},
            ],
        ],
    )

    await HttpxTelegramGateway(
        bot_token="secret-token",
        http_client=client,
        api_base_url="https://telegram.test",
    ).send_message("12345", "Confirma?", markup)
    await client.aclose()

    assert len(requests) == 1
    assert requests[0].url == "https://telegram.test/botsecret-token/sendMessage"
    assert json.loads(requests[0].content) == {
        "chat_id": "12345",
        "text": "Confirma?",
        "reply_markup": markup,
    }


@pytest.mark.asyncio
async def test_gateway_answers_telegram_callback_query() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": True})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://telegram.test",
    )

    await HttpxTelegramGateway(
        bot_token="secret-token",
        http_client=client,
        api_base_url="https://telegram.test",
    ).answer_callback_query("callback-44")
    await client.aclose()

    assert len(requests) == 1
    assert requests[0].url == "https://telegram.test/botsecret-token/answerCallbackQuery"
    assert json.loads(requests[0].content) == {
        "callback_query_id": "callback-44",
    }


@pytest.mark.asyncio
async def test_gateway_rejects_unsuccessful_telegram_response_without_exposing_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "description": "Forbidden"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = HttpxTelegramGateway(
        bot_token="secret-token",
        http_client=client,
    )

    with pytest.raises(TelegramDeliveryError, match="telegram API rejected message") as error:
        await gateway.send_message("12345", "Mensagem")
    await client.aclose()

    assert "secret-token" not in str(error.value)


@pytest.mark.asyncio
async def test_gateway_maps_http_failure_to_controlled_delivery_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"ok": False})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = HttpxTelegramGateway(bot_token="secret-token", http_client=client)

    with pytest.raises(TelegramDeliveryError, match="telegram API request failed"):
        await gateway.send_message("12345", "Mensagem")
    await client.aclose()
