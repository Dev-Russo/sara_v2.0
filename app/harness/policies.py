"""Policies determinísticas do Harness."""

CONFIRMATION_REQUIRED_COMMANDS = frozenset(
    {
        "tasks.delete",
        "tasks.delete_many",
        "tasks.complete_many",
        "tasks.update_many",
        "tasks.reschedule_many",
    }
)


def requires_confirmation(command_type: str) -> bool:
    """Indica se o comando precisa de Human-in-the-Loop."""

    return command_type in CONFIRMATION_REQUIRED_COMMANDS

