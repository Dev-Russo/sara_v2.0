"""Ponto de composição da aplicação FastAPI."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers.health import router as health_router
from app.api.routers.telegram import router as telegram_router
from app.config import Settings, get_settings
from app.graph.checkpoint import GraphInvoker
from app.integrations.telegram.delivery import TelegramResponseDelivery
from app.integrations.telegram.ingress import TelegramIngress
from app.runtime import build_runtime


def create_app(
    settings: Settings | None = None,
    graph: GraphInvoker | None = None,
    telegram_ingress: TelegramIngress | None = None,
    telegram_delivery: TelegramResponseDelivery | None = None,
) -> FastAPI:
    """Monta a aplicação sem criar efeitos externos no import dos módulos."""

    runtime_settings = settings or get_settings()
    runtime = None
    if graph is None or telegram_ingress is None or telegram_delivery is None:
        runtime = build_runtime(runtime_settings)
        selected_graph = graph if graph is not None else runtime.graph
        selected_telegram_ingress = (
            telegram_ingress if telegram_ingress is not None else runtime.telegram_ingress
        )
        selected_telegram_delivery = (
            telegram_delivery if telegram_delivery is not None else runtime.telegram_delivery
        )
    else:
        selected_graph = graph
        selected_telegram_ingress = telegram_ingress
        selected_telegram_delivery = telegram_delivery

    http_client = runtime.telegram_http_client if runtime is not None else None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if http_client is not None:
                await http_client.aclose()

    application = FastAPI(title="SARA 2.0", version="0.1.0", lifespan=lifespan)
    application.state.settings = runtime_settings
    application.state.graph = selected_graph
    application.state.telegram_ingress = selected_telegram_ingress
    application.state.telegram_delivery = selected_telegram_delivery

    application.include_router(health_router)
    application.include_router(telegram_router, prefix="/webhooks")
    return application


app = create_app()
