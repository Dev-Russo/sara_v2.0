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

        if result.command_type in {"tasks.update", "tasks.update_by_id"}:
            if result.status == "failed" and result.error_code in {
                "TASK_NOT_FOUND",
                "TASK_REFERENCE_NOT_FOUND",
            }:
                return ResponseDecision(message="Não encontrei essa tarefa.")
            if result.status == "awaiting_selection":
                items = effect.get("items", [])
                titles = [
                    item.get("title")
                    for item in items
                    if isinstance(item, dict) and isinstance(item.get("title"), str)
                ]
                visible_titles = "; ".join(
                    f"{index}. {title}" for index, title in enumerate(titles[:5], start=1)
                )
                return ResponseDecision(
                    message=(
                        f"Encontrei mais de uma tarefa: {visible_titles}. "
                        "Qual delas deseja atualizar?"
                    ),
                )

            if result.status in {"executed", "duplicate"}:
                kind = effect.get("kind")
                if kind == "task_unchanged":
                    title = effect.get("title")
                    task_label = f": {title}" if isinstance(title, str) else ""
                    return ResponseDecision(
                        message=f"A tarefa j\u00e1 estava com esses dados{task_label}."
                    )
                if kind != "task_updated":
                    return ResponseDecision(
                        message=(
                            "N" + chr(0xE3) + "o consegui confirmar essa atualiza"
                            + chr(0xE7) + chr(0xE3) + "o."
                        ),
                    )
                changed_fields = effect.get("changed_fields", [])
                labels = {
                    "title": "t" + chr(0xED) + "tulo",
                    "description": "descri" + chr(0xE7) + chr(0xE3) + "o",
                    "priority": "prioridade",
                }
                visible_fields = (
                    [
                        labels[field]
                        for field in changed_fields
                        if isinstance(field, str) and field in labels
                    ]
                    if isinstance(changed_fields, list)
                    else []
                )
                title = effect.get("title")
                task_label = f": {title}" if isinstance(title, str) else ""
                prefix = (
                    "A tarefa já estava atualizada"
                    if result.status == "duplicate"
                    else "Tarefa atualizada"
                )
                if not visible_fields:
                    return ResponseDecision(message=f"{prefix}{task_label}.")
                return ResponseDecision(
                    message=(
                        f"{prefix}{task_label}. "
                        f"Campos alterados: {_join_labels(visible_fields)}."
                    ),
                )

        title = effect.get("title")
        if result.command_type == "tasks.create" and isinstance(title, str):
            if result.status == "duplicate":
                return ResponseDecision(message=f"A tarefa jÃ¡ estava criada: {title}.")
            if result.status == "executed":
                return ResponseDecision(message=f"Tarefa criada: {title}.")

        if result.command_type in {"tasks.delete", "tasks.delete_by_id"}:
            if result.status == "failed" and result.error_code == "CONFIRMATION_EXPIRED":
                return ResponseDecision(
                    message=(
                        "A confirma\u00e7\u00e3o expirou. "
                        "Posso preparar a exclus\u00e3o novamente."
                    ),
                )
            if result.status == "failed" and result.error_code == "CONFIRMATION_NOT_FOUND":
                return ResponseDecision(
                    message="Essa confirma\u00e7\u00e3o n\u00e3o est\u00e1 mais dispon\u00edvel.",
                )
            if result.status == "failed" and result.error_code == "CONFIRMATION_ALREADY_RESOLVED":
                return ResponseDecision(
                    message="Essa confirma\u00e7\u00e3o j\u00e1 foi resolvida.",
                )
            if result.status == "awaiting_selection":
                items = effect.get("items", [])
                titles = [
                    item.get("title")
                    for item in items
                    if isinstance(item, dict) and isinstance(item.get("title"), str)
                ]
                visible_titles = "; ".join(
                    f"{index}. {title}" for index, title in enumerate(titles[:5], start=1)
                )
                return ResponseDecision(
                    message=(
                        f"Encontrei mais de uma tarefa: {visible_titles}. "
                        "Qual delas deseja excluir?"
                    ),
                )
            if result.status == "awaiting_confirmation":
                title = effect.get("title")
                task_label = f' "{title}"' if isinstance(title, str) else ""
                return ResponseDecision(
                    message=(
                        f"Confirma a exclusão da tarefa{task_label}? "
                        "Essa ação não poderá ser desfeita."
                    ),
                )
            if result.status == "rejected" and result.error_code == "CONFIRMATION_CANCELLED":
                return ResponseDecision(message="Exclusão cancelada.")
            if result.status == "failed" and result.error_code in {
                "TASK_NOT_FOUND",
                "TASK_REFERENCE_NOT_FOUND",
            }:
                return ResponseDecision(message="Não encontrei essa tarefa.")
            if result.status in {"executed", "duplicate"}:
                title = effect.get("title")
                if isinstance(title, str):
                    prefix = (
                        "A tarefa já estava excluída"
                        if result.status == "duplicate"
                        else "Tarefa excluída"
                    )
                    return ResponseDecision(message=f"{prefix}: {title}.")
                return ResponseDecision(message="Tarefa excluída.")

        if result.command_type in {"tasks.complete", "tasks.complete_by_id"}:
            if result.status == "awaiting_selection":
                items = effect.get("items", [])
                titles = [
                    item.get("title")
                    for item in items
                    if isinstance(item, dict) and isinstance(item.get("title"), str)
                ]
                visible_titles = "; ".join(
                    f"{index}. {title}" for index, title in enumerate(titles[:5], start=1)
                )
                return ResponseDecision(
                    message=(
                        f"Encontrei mais de uma tarefa: {visible_titles}. "
                        "Qual delas deseja concluir?"
                    ),
                )
            if result.status == "failed" and result.error_code == "TASK_REFERENCE_NOT_FOUND":
                return ResponseDecision(
                    message=(
                        "N\u00e3o encontrei essa tarefa pendente. "
                        "Pode descrever melhor a tarefa?"
                    ),
                )
            if result.status == "failed" and result.error_code == "TASK_NOT_FOUND":
                return ResponseDecision(message="NÃ£o encontrei essa tarefa pendente.")
            if isinstance(title, str):
                if result.status == "duplicate":
                    return ResponseDecision(
                        message=f"A tarefa j\u00e1 estava conclu\u00edda: {title}.",
                    )
                if result.status == "executed":
                    return ResponseDecision(message=f"Tarefa conclu\u00edda: {title}.")

        if result.status == "rejected":
            return ResponseDecision(message="NÃ£o foi possÃ­vel executar esse comando.")
        if result.status == "awaiting_confirmation":
            return ResponseDecision(message="Preciso da sua confirmaÃ§Ã£o para continuar.")
        if result.status == "failed":
            return ResponseDecision(message="A execuÃ§Ã£o da tarefa falhou.")
        return ResponseDecision(message="Comando executado com sucesso.")


def _join_labels(labels: list[str]) -> str:
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} e {labels[1]}"
    return f"{', '.join(labels[:-1])} e {labels[-1]}"
