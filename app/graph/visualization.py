"""Gera relatórios visuais diretamente do Graph compilado."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from langgraph.graph.state import CompiledStateGraph

from app.config import get_settings
from app.runtime import build_runtime_graph


@dataclass(frozen=True, slots=True)
class GraphReport:
    """Arquivos gerados a partir da topologia real do Graph."""

    mermaid_path: Path
    png_path: Path | None = None


def write_graph_report(
    graph: CompiledStateGraph,
    output_dir: Path,
    *,
    name: str = "sara-graph",
    render_png: bool = False,
    mermaid_cli: str | None = None,
) -> GraphReport:
    """Escreve Mermaid e, opcionalmente, PNG sem reescrever os nós manualmente."""

    output_dir.mkdir(parents=True, exist_ok=True)
    drawable_graph = graph.get_graph()
    mermaid_path = output_dir / f"{name}.mmd"
    mermaid_path.write_text(drawable_graph.draw_mermaid(), encoding="utf-8")

    png_path: Path | None = None
    if render_png:
        png_path = output_dir / f"{name}.png"
        renderer = mermaid_cli or shutil.which("mmdc") or shutil.which("mmdc.cmd")
        if renderer is None:
            raise RuntimeError(
                "PNG requires the local Mermaid CLI (mmdc); the .mmd file was generated"
            )
        subprocess.run(
            [
                renderer,
                "-i",
                str(mermaid_path),
                "-o",
                str(png_path),
                "-b",
                "transparent",
            ],
            check=True,
        )

    return GraphReport(mermaid_path=mermaid_path, png_path=png_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/graph"),
        help="Diretório onde os relatórios serão gravados.",
    )
    parser.add_argument(
        "--name",
        default="sara-graph",
        help="Nome base dos arquivos gerados.",
    )
    parser.add_argument(
        "--png",
        action="store_true",
        help="Também gera PNG usando um mmdc local.",
    )
    args = parser.parse_args(argv)

    graph = build_runtime_graph(get_settings())
    if graph is None:
        parser.error("configure LLM_API_KEY e LLM_MODEL antes de gerar o relatório")

    try:
        report = write_graph_report(
            graph,
            args.output_dir,
            name=args.name,
            render_png=args.png,
        )
    except RuntimeError as error:
        parser.error(str(error))
    print(f"Mermaid: {report.mermaid_path}")
    if report.png_path is not None:
        print(f"PNG: {report.png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
