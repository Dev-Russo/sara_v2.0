"""Roteamento inicial para um fluxo sem agente ativo."""

from typing import Literal

FlowType = Literal["task", "planning", "review", "reminder"]


def select_flow(text: str) -> FlowType | None:
    """Ponto inicial determinístico; a classificação por LLM entra depois desta seam."""

    normalized = text.casefold()
    if "planej" in normalized:
        return "planning"
    if "revis" in normalized:
        return "review"
    if "lembrete" in normalized:
        return "reminder"
    if normalized.strip():
        return "task"
    return None

