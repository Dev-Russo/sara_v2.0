"""Chaves idempotentes para janelas de execução agendada."""

from hashlib import sha256


def scheduled_idempotency_key(resource: str, window: str) -> str:
    """Gera chave estável sem incluir conteúdo pessoal desnecessário."""

    return sha256(f"{resource}:{window}".encode()).hexdigest()

