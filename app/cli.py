"""Canal interativo local que reutiliza o mesmo Graph da aplicação."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from langgraph.graph.state import CompiledStateGraph

from app.config import Settings, get_settings
from app.graph.state import GraphState
from app.runtime import build_runtime_graph
from app.schemas.events import ExecutionContext, MessageEvent

logger = logging.getLogger(__name__)
EXIT_COMMANDS = {"/exit", "/quit"}


@dataclass(slots=True)
class CliSession:
    """Mantém identidade e fluxo da conversa durante uma sessão do terminal."""

    graph: CompiledStateGraph
    user_id: UUID
    graph_thread_id: str = field(default_factory=lambda: f"cli:{uuid4()}")
    active_flow: str | None = None

    async def process(self, text: str) -> str:
        """Processa uma mensagem pelo Graph e devolve somente a resposta final."""

        normalized_text = text.strip()
        if not normalized_text:
            return "Digite uma mensagem para continuar."

        turn_id = uuid4()
        event = MessageEvent(
            event_id=f"cli:{turn_id}",
            user_id=self.user_id,
            text=normalized_text,
            received_at=datetime.now(UTC),
            source="cli",
        )
        context = ExecutionContext(
            user_id=self.user_id,
            graph_thread_id=self.graph_thread_id,
            correlation_id=f"cli:{turn_id}",
            idempotency_key=f"cli:{turn_id}",
            source="cli",
        )
        state: GraphState = {"event": event, "context": context}
        if self.active_flow is not None:
            state["active_flow"] = self.active_flow

        result = await self.graph.ainvoke(state)
        self.active_flow = result.get("active_flow")
        response = result.get("response_decision")
        if response is None:
            return "Não consegui produzir uma resposta."
        return response.message


async def run_cli(settings: Settings | None = None) -> int:
    """Executa o loop interativo local usando o adapter real de LLM."""

    runtime_settings = settings or get_settings()
    graph = build_runtime_graph(runtime_settings)
    if graph is None:
        print("Configure LLM_API_KEY e LLM_MODEL no .env antes de iniciar o CLI.")
        return 1

    session = CliSession(graph=graph, user_id=runtime_settings.cli_user_id)
    print("SARA CLI. Digite /exit para sair.")
    while True:
        try:
            text = input("Você> ")
        except EOFError:
            print()
            return 0

        if text.strip().casefold() in EXIT_COMMANDS:
            return 0
        try:
            print(f"SARA> {await session.process(text)}")
        except Exception:
            logger.exception("CLI message processing failed")
            print("SARA> Não consegui processar essa mensagem agora.")


def main() -> None:
    raise SystemExit(asyncio.run(run_cli()))


if __name__ == "__main__":
    main()
