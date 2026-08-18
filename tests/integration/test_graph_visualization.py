from pathlib import Path

from app.agents.task import TaskAgent
from app.graph.builder import build_graph
from app.graph.visualization import write_graph_report
from app.harness.registry import CommandRegistry
from app.harness.service import Harness


class UnusedLLM:
    async def complete(self, *, system_prompt: str, user_message: str) -> str:
        raise AssertionError("visualization must not call the LLM")


def test_graph_report_is_generated_from_compiled_graph(tmp_path: Path) -> None:
    graph = build_graph(
        task_agent=TaskAgent(UnusedLLM()),
        harness=Harness(CommandRegistry()),
    )

    report = write_graph_report(graph, tmp_path)

    assert report.mermaid_path.exists()
    mermaid = report.mermaid_path.read_text(encoding="utf-8")
    assert "task_agent" in mermaid
    assert "execute_command" in mermaid
    assert "render_response" in mermaid
    assert report.png_path is None
