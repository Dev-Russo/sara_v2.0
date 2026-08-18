"""Ponto de composição da aplicação FastAPI."""

from fastapi import FastAPI

from app.api.routers.health import router as health_router
from app.api.routers.telegram import router as telegram_router
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Monta a aplicação sem criar conexões ou efeitos colaterais no import."""

    application = FastAPI(title="SARA 2.0", version="0.1.0")
    application.state.settings = settings or get_settings()
    application.include_router(health_router)
    application.include_router(telegram_router, prefix="/webhooks")
    return application


app = create_app()

