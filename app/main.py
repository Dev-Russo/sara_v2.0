"""Ponto de composição da aplicação FastAPI."""

from fastapi import FastAPI
from langgraph.graph.state import CompiledStateGraph

from app.api.routers.health import router as health_router
from app.api.routers.telegram import router as telegram_router
from app.config import Settings, get_settings
from app.integrations.telegram.ingress import TelegramIngress
from app.runtime import build_runtime


def create_app(
    settings: Settings | None = None,
    graph: CompiledStateGraph | None = None,
    telegram_ingress: TelegramIngress | None = None,
) -> FastAPI:
    """Monta a aplicação sem criar conexões ou efeitos colaterais no import."""

    application = FastAPI(title="SARA 2.0", version="0.1.0")
    runtime_settings = settings or get_settings()
    if graph is None or telegram_ingress is None:
        runtime = build_runtime(runtime_settings)
        selected_graph = graph if graph is not None else runtime.graph
        selected_telegram_ingress = (
            telegram_ingress if telegram_ingress is not None else runtime.telegram_ingress
        )
    else:
        selected_graph = graph
        selected_telegram_ingress = telegram_ingress

    application.state.settings = runtime_settings
    application.state.graph = selected_graph
    application.state.telegram_ingress = selected_telegram_ingress
    application.include_router(health_router)
    application.include_router(telegram_router, prefix="/webhooks")
    return application


app = create_app()
