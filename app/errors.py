"""Erros de domínio esperados pelos casos de uso."""


class InvalidTaskTimeRangeError(ValueError):
    """Indica que o horário final ficou antes do horário inicial."""
