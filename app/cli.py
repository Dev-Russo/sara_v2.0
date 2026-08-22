"""Canal interativo local que reutiliza o mesmo Graph da aplicação."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from langgraph.graph.state import CompiledStateGraph

from app.config import Settings, get_settings
from app.graph.state import GraphState
from app.harness.confirmation import normalize_confirmation
from app.runtime import build_runtime_graph
from app.schemas.commands import TaskDeletePayload, TaskUpdatePayload
from app.schemas.events import ConfirmationEvent, ExecutionContext, MessageEvent
from app.schemas.tasks import TaskCandidate

logger = logging.getLogger(__name__)
EXIT_COMMANDS = {"/exit", "/quit"}


@dataclass(slots=True)
class CliSession:
    """Mantém identidade e fluxo da conversa durante uma sessão do terminal."""

    graph: CompiledStateGraph
    user_id: UUID
    graph_thread_id: str = field(default_factory=lambda: f"cli:{uuid4()}")
    active_flow: str | None = None
    pending_task_candidates: list[TaskCandidate] = field(default_factory=list)
    pending_task_update: TaskUpdatePayload | None = None
    pending_task_delete: TaskDeletePayload | None = None
    pending_confirmation_id: UUID | None = None
    debug: bool = False
    trace_sink: Callable[[str], None] = print

    async def process(self, text: str) -> str:
        """Processa uma mensagem pelo Graph e devolve somente a resposta final."""

        normalized_text = text.strip()
        if not normalized_text:
            return "Digite uma mensagem para continuar."

        turn_id = uuid4()
        confirmation_decision = (
            normalize_confirmation(normalized_text)
            if self.pending_confirmation_id is not None
            else None
        )
        if confirmation_decision is not None:
            event = ConfirmationEvent(
                confirmation_id=self.pending_confirmation_id,
                user_id=self.user_id,
                decision=confirmation_decision,
                received_at=datetime.now(UTC),
                source="cli",
            )
        else:
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
        if self.pending_task_candidates:
            state["pending_task_candidates"] = self.pending_task_candidates
        if self.pending_task_update is not None:
            state["pending_task_update"] = self.pending_task_update
        if self.pending_task_delete is not None:
            state["pending_task_delete"] = self.pending_task_delete
        if self.pending_confirmation_id is not None:
            state["pending_confirmation_id"] = self.pending_confirmation_id

        result = await self.graph.ainvoke(state)
        self.active_flow = result.get("active_flow")
        self.pending_task_candidates = result.get(
            "pending_task_candidates",
            self.pending_task_candidates,
        )
        self.pending_task_update = result.get(
            "pending_task_update",
            self.pending_task_update,
        )
        self.pending_task_delete = result.get(
            "pending_task_delete",
            self.pending_task_delete,
        )
        self.pending_confirmation_id = result.get(
            "pending_confirmation_id",
            self.pending_confirmation_id,
        )
        if self.debug:
            self._trace_model("agent_decision", result.get("agent_decision"))
            self._trace_model("resolved_command", result.get("resolved_command"))
            self._trace_model("harness_result", result.get("harness_result"))
        response = result.get("response_decision")
        if response is None:
            return "Não consegui produzir uma resposta."
        if self.debug:
            self.trace_sink(f"[debug] response: {response.message}")
        return response.message

    def _trace_model(self, label: str, value: object) -> None:
        if value is None:
            self.trace_sink(f"[debug] {label}: null")
            return
        payload = value.model_dump(mode="json")
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.trace_sink(f"[debug] {label}: {serialized}")


async def run_cli(settings: Settings | None = None, *, debug: bool = False) -> int:
    """Executa o loop interativo local usando o adapter real de LLM."""

    runtime_settings = settings or get_settings()
    graph = build_runtime_graph(runtime_settings)
    if graph is None:
        print("Configure LLM_API_KEY e LLM_MODEL no .env antes de iniciar o CLI.")
        return 1

    session = CliSession(
        graph=graph,
        user_id=runtime_settings.cli_user_id,
        debug=debug,
    )
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Executa a SARA no terminal.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="mostra a decisao do agente e o resultado do Harness a cada mensagem",
    )
    args = parser.parse_args(argv)
    raise SystemExit(asyncio.run(run_cli(debug=args.debug)))


if __name__ == "__main__":
    main()
