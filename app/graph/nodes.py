"""Nós do Graph; cada nó recebe e devolve estado estruturado."""

from typing import Literal

from app.agents.base import Agent
from app.agents.response import ResponseAgent
from app.agents.supervisor import select_flow
from app.graph.state import GraphState
from app.harness.service import Harness
from app.schemas.results import ResponseDecision

FlowRoute = Literal["task", "unsupported"]
DecisionRoute = Literal["execute", "respond"]


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
