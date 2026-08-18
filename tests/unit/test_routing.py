from app.graph.routing import route_event


def test_confirmation_has_priority_over_active_flow() -> None:
    assert route_event(has_pending_confirmation=True, active_flow=True) == "confirmation"


def test_active_flow_does_not_return_to_supervisor() -> None:
    assert route_event(has_pending_confirmation=False, active_flow=True) == "active_agent"


def test_idle_conversation_uses_supervisor() -> None:
    assert route_event(has_pending_confirmation=False, active_flow=False) == "supervisor"

