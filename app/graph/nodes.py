"""Nós do Graph; cada nó deverá receber e devolver estado estruturado."""

from app.graph.state import GraphState


async def load_session(state: GraphState) -> GraphState:
    """Seam para carregar ConversationSession e confirmação pendente."""

    return state


async def normalize_decision(state: GraphState) -> GraphState:
    """Valida a decisão do agente antes de entregá-la ao Harness."""

    return state

