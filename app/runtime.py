"""Composição das dependências reais usadas pelos canais da aplicação."""

from langgraph.graph.state import CompiledStateGraph

from app.agents.task import TaskAgent
from app.config import Settings
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
