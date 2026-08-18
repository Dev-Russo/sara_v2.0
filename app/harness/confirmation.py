"""Normalização de decisões sobre confirmações pendentes."""

from typing import Literal

ConfirmationDecision = Literal["confirm", "cancel"]


def normalize_confirmation(text: str) -> ConfirmationDecision | None:
    """Aceita apenas respostas curtas e inequívocas."""

    normalized = " ".join(text.casefold().split())
    if normalized in {"sim", "confirmar", "confirmo", "s", "yes"}:
        return "confirm"
    if normalized in {"não", "nao", "cancelar", "cancelo", "n", "no"}:
        return "cancel"
    return None

