"""Regras de roteamento que não dependem de linguagem natural."""

from typing import Literal

Route = Literal["confirmation", "active_agent", "supervisor"]


def route_event(*, has_pending_confirmation: bool, active_flow: bool) -> Route:
    """Escolhe a próxima seam do Graph na ordem definida pelo domínio."""

    if has_pending_confirmation:
        return "confirmation"
    if active_flow:
        return "active_agent"
    return "supervisor"

