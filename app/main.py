"""Ponto de composição da aplicação FastAPI."""

from fastapi import FastAPI
from langgraph.graph.state import CompiledStateGraph

from app.api.routers.health import router as health_router
from app.api.routers.telegram import router as telegram_router
from app.config import Settings, get_settings
from app.runtime import build_runtime_graph


def create_app(
    settings: Settings | None = None,
    graph: CompiledStateGraph | None = None,
) -> FastAPI:
    """Monta a aplicação sem criar conexões ou efeitos colaterais no import."""

    application = FastAPI(title="SARA 2.0", version="0.1.0")
    runtime_settings = settings or get_settings()
    application.state.settings = runtime_settings
    application.state.graph = graph or build_runtime_graph(runtime_settings)
    application.include_router(health_router)
    application.include_router(telegram_router, prefix="/webhooks")
    return application


app = create_app()
