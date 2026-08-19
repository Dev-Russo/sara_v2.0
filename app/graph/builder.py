"""Composição do Graph, mantida pequena e sem regra de domínio."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.base import Agent
from app.agents.response import DeterministicResponseAgent, ResponseAgent
from app.graph.nodes import (
    execute_command,
    load_session,
    normalize_decision,
    render_response,
    resolve_pending_task_choice,
    route_decision,
    route_flow,
    route_harness_result,
    run_task_agent,
    store_task_completion_candidates,
    unsupported_flow,
)
from app.graph.state import GraphState
from app.harness.service import Harness


def build_graph(
    *,
    task_agent: Agent,
    harness: Harness,
    response_agent: ResponseAgent | None = None,
) -> CompiledStateGraph:
    """Monta o fluxo de captura de tarefa com dependências explícitas."""

    graph = StateGraph(GraphState)
    selected_response_agent = response_agent or DeterministicResponseAgent()

    async def task_agent_node(state: GraphState) -> GraphState:
        return await run_task_agent(state, task_agent)

    async def harness_node(state: GraphState) -> GraphState:
        return await execute_command(state, harness)

    async def response_node(state: GraphState) -> GraphState:
        return await render_response(state, selected_response_agent)

    async def selection_storage_node(state: GraphState) -> GraphState:
        return await store_task_completion_candidates(state)

    async def pending_choice_node(state: GraphState) -> GraphState:
        return await resolve_pending_task_choice(state, harness)

    graph.add_node("load_session", load_session)
    graph.add_node("task_agent", task_agent_node)
    graph.add_node("normalize_decision", normalize_decision)
    graph.add_node("execute_command", harness_node)
    graph.add_node("store_task_completion_candidates", selection_storage_node)
    graph.add_node("resolve_pending_task_choice", pending_choice_node)
    graph.add_node("unsupported_flow", unsupported_flow)
    graph.add_node("render_response", response_node)

    graph.add_edge(START, "load_session")
    graph.add_conditional_edges(
        "load_session",
        route_flow,
        {
            "task": "task_agent",
            "pending_choice": "resolve_pending_task_choice",
            "unsupported": "unsupported_flow",
        },
    )
    graph.add_edge("task_agent", "normalize_decision")
    graph.add_conditional_edges(
        "normalize_decision",
        route_decision,
        {"execute": "execute_command", "respond": "render_response"},
    )
    graph.add_conditional_edges(
        "execute_command",
        route_harness_result,
        {
            "store_selection": "store_task_completion_candidates",
            "respond": "render_response",
        },
    )
    graph.add_edge("store_task_completion_candidates", "render_response")
    graph.add_edge("resolve_pending_task_choice", "render_response")
    graph.add_edge("unsupported_flow", "render_response")
    graph.add_edge("render_response", END)

    return graph.compile()
