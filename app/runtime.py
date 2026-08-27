"""Composição das dependências reais usadas pelos canais da aplicação."""

from dataclasses import dataclass

from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.task import TaskAgent
from app.config import Settings
from app.db.session import create_session_factory
from app.graph.builder import build_graph
from app.harness.handlers import build_task_confirmation_resolver, register_task_handlers
from app.harness.registry import CommandRegistry
from app.harness.service import Harness
from app.integrations.llm.anthropic_adapter import AnthropicAdapter
from app.integrations.telegram.ingress import TelegramIngressAdapter
from app.services.tasks import TaskService


@dataclass(frozen=True, slots=True)
class RuntimeComponents:
    """Dependências compartilhadas pelos adapters de entrada e pelo Graph."""

    graph: CompiledStateGraph | None
    telegram_ingress: TelegramIngressAdapter


def build_runtime(settings: Settings) -> RuntimeComponents:
    """Compõe as dependências reais usando uma única fábrica de sessões."""

    session_factory = create_session_factory(settings)
    graph = (
        _build_graph(settings, session_factory)
        if settings.llm_api_key and settings.llm_model
        else None
    )
    return RuntimeComponents(
        graph=graph,
        telegram_ingress=TelegramIngressAdapter(session_factory),
    )


def build_runtime_graph(settings: Settings) -> CompiledStateGraph | None:
    """Compõe o caminho real quando as credenciais do LLM estão configuradas."""

    if not settings.llm_api_key or not settings.llm_model:
        return None

    return _build_graph(settings, create_session_factory(settings))


def _build_graph(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> CompiledStateGraph:
    task_service = TaskService(session_factory, timezone=settings.timezone)
    registry = CommandRegistry()
    register_task_handlers(registry, task_service)
    harness = Harness(
        registry,
        confirmation_resolver=build_task_confirmation_resolver(task_service),
    )
    task_agent = TaskAgent(
        AnthropicAdapter(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        ),
        timezone=settings.timezone,
    )
    return build_graph(task_agent=task_agent, harness=harness)
