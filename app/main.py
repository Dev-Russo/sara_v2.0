"""Ponto de composição da aplicação FastAPI."""

from fastapi import FastAPI
from langgraph.graph.state import CompiledStateGraph

from app.agents.task import TaskAgent
from app.api.routers.health import router as health_router
from app.api.routers.telegram import router as telegram_router
from app.config import Settings, get_settings
from app.db.session import create_session_factory
from app.graph.builder import build_graph
from app.harness.handlers import register_task_handlers
from app.harness.registry import CommandRegistry
from app.harness.service import Harness
from app.integrations.llm.anthropic_adapter import AnthropicAdapter
from app.services.tasks import TaskService


def build_runtime_graph(settings: Settings) -> CompiledStateGraph | None:
    """Compõe o caminho real quando as credenciais do LLM estão configuradas."""

    if not settings.llm_api_key or not settings.llm_model:
        return None

    session_factory = create_session_factory(settings)
    task_service = TaskService(session_factory)
    registry = CommandRegistry()
    register_task_handlers(registry, task_service)
    harness = Harness(registry)
    task_agent = TaskAgent(
        AnthropicAdapter(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        ),
    )
    return build_graph(task_agent=task_agent, harness=harness)


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
