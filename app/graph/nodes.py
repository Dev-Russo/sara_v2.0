"""Nós do Graph; cada nó recebe e devolve estado estruturado."""

import re
import unicodedata
from typing import Literal
from uuid import UUID

from app.agents.base import Agent
from app.agents.response import ResponseAgent
from app.agents.supervisor import select_flow
from app.graph.state import GraphState
from app.harness.service import Harness
from app.schemas.commands import (
    TaskIdPayload,
    TasksCompleteByIdCommand,
    TasksUpdateByIdCommand,
    TasksUpdateCommand,
    TaskUpdateByIdPayload,
)
from app.schemas.results import ResponseDecision
from app.schemas.tasks import TaskCandidate

FlowRoute = Literal["task", "pending_choice", "unsupported"]
DecisionRoute = Literal["execute", "respond"]
HarnessRoute = Literal["store_selection", "respond"]


async def load_session(state: GraphState) -> GraphState:
    """Valida o contexto confiável e seleciona o fluxo inicial."""

    event = state["event"]
    context = state["context"]
    if event.user_id != context.user_id:
        raise ValueError("event and execution context must belong to the same user")

    active_flow = state.get("active_flow")
    if active_flow is None:
        active_flow = select_flow(event.text)
    return {"active_flow": active_flow}


def route_flow(state: GraphState) -> FlowRoute:
    """Encaminha somente o fluxo de tarefas implementado nesta fatia."""

    if state.get("pending_task_candidates"):
        return "pending_choice"
    return "task" if state.get("active_flow") == "task" else "unsupported"


async def run_task_agent(state: GraphState, agent: Agent) -> GraphState:
    """Pede uma decisão ao TaskAgent sem conceder acesso a efeitos colaterais."""

    decision = await agent.decide(state["event"], state["context"])
    return {"agent_decision": decision}


async def normalize_decision(state: GraphState) -> GraphState:
    """Mantém a decisão validada como entrada do roteamento do Harness."""

    return state


def route_decision(state: GraphState) -> DecisionRoute:
    """Distingue conversa do agente de comando pronto para o Harness."""

    decision = state.get("agent_decision")
    return "execute" if decision is not None and decision.command is not None else "respond"


async def execute_command(state: GraphState, harness: Harness) -> GraphState:
    """Entrega o comando ao Harness, a única porta de mutação iniciada pelo agente."""

    decision = state["agent_decision"]
    if decision.command is None:
        return state
    result = await harness.handle(decision.command, state["context"])
    return {"harness_result": result}


def route_harness_result(state: GraphState) -> HarnessRoute:
    """Envia o resultado de busca para resoluÃ§Ã£o antes da resposta final."""

    result = state.get("harness_result")
    if (
        result is not None
        and result.command_type in {"tasks.complete", "tasks.update"}
        and result.status == "awaiting_selection"
    ):
        return "store_selection"
    return "respond"


async def store_task_reference_candidates(state: GraphState) -> GraphState:
    """Conclui automaticamente somente quando a busca retorna um candidato."""

    result = state["harness_result"]
    effect = result.effect or {}
    raw_items = effect.get("items", [])
    if not isinstance(raw_items, list):
        return {"pending_task_candidates": [], "pending_task_update": None}

    candidates = [
        TaskCandidate.model_validate(item)
        for item in raw_items
        if isinstance(item, dict)
    ]
    decision = state.get("agent_decision")
    command = decision.command if decision is not None else None
    pending_update = command.payload if isinstance(command, TasksUpdateCommand) else None
    return {
        "pending_task_candidates": candidates,
        "pending_task_update": pending_update,
    }


async def resolve_pending_task_choice(state: GraphState, harness: Harness) -> GraphState:
    """Conclui a opÃ§Ã£o escolhida sem pedir nova interpretaÃ§Ã£o ao agente."""

    candidates = state.get("pending_task_candidates", [])
    selected = _select_task_candidate(state["event"].text, candidates)
    if selected is None:
        return {
            "response_decision": ResponseDecision(
                message=_task_choice_message(candidates),
            ),
        }

    pending_update = state.get("pending_task_update")
    if pending_update is not None:
        update_payload = pending_update.model_dump(mode="python", exclude_unset=True)
        update_payload.pop("query", None)
        update_payload["task_id"] = selected.id
        command = TasksUpdateByIdCommand(
            type="tasks.update_by_id",
            payload=TaskUpdateByIdPayload.model_validate(update_payload),
        )
        update_result = await harness.handle(
            command,
            _resolved_context(state, "tasks.update", selected.id),
        )
        return {
            "harness_result": update_result,
            "pending_task_candidates": [],
            "pending_task_update": None,
            "resolved_command": command,
        }

    command = TasksCompleteByIdCommand(
        type="tasks.complete_by_id",
        payload=TaskIdPayload(task_id=selected.id),
    )
    completion_result = await harness.handle(
        command,
        _resolved_context(state, "tasks.complete", selected.id),
    )
    return {
        "harness_result": completion_result,
        "pending_task_candidates": [],
        "pending_task_update": None,
        "resolved_command": command,
    }


async def unsupported_flow(state: GraphState) -> GraphState:
    """Fallback transitório enquanto o Supervisor não encaminha outros agentes."""

    flow = state.get("active_flow") or "conversation"
    return {
        "response_decision": ResponseDecision(
            message=f"O fluxo de {flow} ainda não está disponível.",
        ),
    }


async def render_response(state: GraphState, response_agent: ResponseAgent) -> GraphState:
    """Entrega resultados ao ResponseAgent sem conhecer regras de apresentação."""

    if state.get("response_decision") is not None:
        return state

    result = state.get("harness_result")
    if result is not None:
        response = await response_agent.respond(result, state["context"])
        return {"response_decision": response}

    decision = state.get("agent_decision")
    message = (
        decision.message
        if decision and decision.message
        else "Não consegui processar essa solicitação."
    )
    return {
        "response_decision": ResponseDecision(message=message),
    }


def _resolved_context(state: GraphState, command_type: str, task_id: UUID):
    context = state["context"]
    return context.model_copy(
        update={"idempotency_key": f"{context.idempotency_key}:{command_type}:{task_id}"},
    )


def _select_task_candidate(text: str, candidates: list[TaskCandidate]) -> TaskCandidate | None:
    normalized = _normalize_task_text(text)
    ordinal_map = {
        "primeira": 1,
        "primeiro": 1,
        "segunda": 2,
        "segundo": 2,
        "terceira": 3,
        "terceiro": 3,
        "quarta": 4,
        "quarto": 4,
    }
    selected_number = next(
        (number for word, number in ordinal_map.items() if re.search(rf"\b{word}\b", normalized)),
        None,
    )
    if selected_number is None:
        match = re.search(r"\b([1-9][0-9]*)\b", normalized)
        selected_number = int(match.group(1)) if match else None
    if selected_number is not None and 1 <= selected_number <= len(candidates):
        return candidates[selected_number - 1]

    matching = [
        candidate
        for candidate in candidates
        if _normalize_task_text(candidate.title) in normalized
    ]
    return matching[0] if len(matching) == 1 else None


def _task_choice_message(candidates: list[TaskCandidate]) -> str:
    options = "; ".join(
        f"{index}. {candidate.title}" for index, candidate in enumerate(candidates, start=1)
    )
    return f"Encontrei mais de uma tarefa: {options}. Qual delas deseja concluir?"


def _normalize_task_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return " ".join(normalized.encode("ascii", "ignore").decode("ascii").split())
