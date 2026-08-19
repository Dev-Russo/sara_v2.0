"""Seam do ResponseAgent, grounded no HarnessResult."""

from typing import Protocol

from app.schemas.events import ExecutionContext
from app.schemas.results import HarnessResult, ResponseDecision


class ResponseAgent(Protocol):
    async def respond(
        self,
        result: HarnessResult,
        context: ExecutionContext,
    ) -> ResponseDecision:
        """Verbaliza apenas efeitos presentes no resultado estruturado."""


class DeterministicResponseAgent:
    """Fallback local que verbaliza somente os efeitos conhecidos do Harness."""

    async def respond(
        self,
        result: HarnessResult,
        context: ExecutionContext,
    ) -> ResponseDecision:
        del context
        effect = result.effect or {}

        if result.command_type == "tasks.list" and result.status == "executed":
            total = effect.get("total", 0)
            items = effect.get("items", [])
            titles = [
                item.get("title")
                for item in items
                if isinstance(item, dict) and isinstance(item.get("title"), str)
            ]
            if total == 0:
                return ResponseDecision(message="NÃ£o encontrei tarefas para essa consulta.")
            if total == 1 and titles:
                return ResponseDecision(message=f"Encontrei 1 tarefa: {titles[0]}.")
            if not titles:
                return ResponseDecision(message=f"Encontrei {total} tarefas.")
            visible_titles = ", ".join(titles[:5])
            suffix = "" if len(titles) <= 5 else ", entre outras"
            return ResponseDecision(
                message=f"Encontrei {total} tarefas: {visible_titles}{suffix}.",
            )

        title = effect.get("title")
        if result.command_type == "tasks.create" and isinstance(title, str):
            if result.status == "duplicate":
                return ResponseDecision(message=f"A tarefa jÃ¡ estava criada: {title}.")
            if result.status == "executed":
                return ResponseDecision(message=f"Tarefa criada: {title}.")

        if result.status == "rejected":
            return ResponseDecision(message="NÃ£o foi possÃ­vel executar esse comando.")
        if result.status == "awaiting_confirmation":
            return ResponseDecision(message="Preciso da sua confirmaÃ§Ã£o para continuar.")
        if result.status == "failed":
            return ResponseDecision(message="A execuÃ§Ã£o da tarefa falhou.")
        return ResponseDecision(message="Comando executado com sucesso.")
