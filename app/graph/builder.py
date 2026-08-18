"""Composição do Graph, mantida pequena e sem regra de domínio."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.base import Agent
from app.graph.nodes import (
    execute_command,
    load_session,
    normalize_decision,
    render_response,
    route_decision,
    route_flow,
    run_task_agent,
    unsupported_flow,
)
from app.graph.state import GraphState
from app.harness.service import Harness


def build_graph(*, task_agent: Agent, harness: Harness) -> CompiledStateGraph:
    """Monta o fluxo de captura de tarefa com dependências explícitas."""

    graph = StateGraph(GraphState)

    async def task_agent_node(state: GraphState) -> GraphState:
        return await run_task_agent(state, task_agent)

    async def harness_node(state: GraphState) -> GraphState:
        return await execute_command(state, harness)

    graph.add_node("load_session", load_session)
    graph.add_node("task_agent", task_agent_node)
    graph.add_node("normalize_decision", normalize_decision)
    graph.add_node("execute_command", harness_node)
    graph.add_node("unsupported_flow", unsupported_flow)
    graph.add_node("render_response", render_response)

    graph.add_edge(START, "load_session")
    graph.add_conditional_edges(
        "load_session",
        route_flow,
        {"task": "task_agent", "unsupported": "unsupported_flow"},
    )
    graph.add_edge("task_agent", "normalize_decision")
    graph.add_conditional_edges(
        "normalize_decision",
        route_decision,
        {"execute": "execute_command", "respond": "render_response"},
    )
    graph.add_edge("execute_command", "render_response")
    graph.add_edge("unsupported_flow", "render_response")
    graph.add_edge("render_response", END)

    return graph.compile()
