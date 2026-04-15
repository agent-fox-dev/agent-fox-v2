"""CLI command for status report: agent-fox status.

Displays a progress dashboard showing task counts, token usage,
cost, and problem tasks.

Requirements: 07-REQ-1.1, 07-REQ-1.2, 07-REQ-1.3, 07-REQ-3.1,
              23-REQ-3.1, 23-REQ-8.1, 43-REQ-1.4, 43-REQ-2.2
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

import click
from rich.console import Console

from agent_fox.cli import handle_agent_fox_errors
from agent_fox.core.paths import AGENT_FOX_DIR, DEFAULT_DB_PATH
from agent_fox.reporting.formatters import (
    OutputFormat,
    get_formatter,
    write_output,
)
from agent_fox.reporting.status import generate_status as _reporting_generate_status

logger = logging.getLogger(__name__)


def generate_status(
    db_path: Path | None = None,
) -> None:
    """Graceful existence check for the DuckDB status file (TS-105-E6).

    Returns ``None`` when ``db_path`` is absent so ``af status`` can display
    "No plan found" instead of raising an exception.  The full status report
    is rendered by ``_reporting_generate_status`` inside ``status_cmd``, which
    accepts an optional DuckDB connection for plan_nodes queries.

    Requirements: 105-REQ-6.E1
    """
    if db_path is None or not Path(db_path).exists():
        return None
    return None


def _get_readonly_conn():
    """Open a read-only DuckDB connection.

    Returns None if the database does not exist or cannot be opened
    (e.g. no write-ahead log available for read-only access).

    Requirement: 43-REQ-1.4
    """
    try:
        import duckdb

        if not DEFAULT_DB_PATH.exists():
            return None
        return duckdb.connect(str(DEFAULT_DB_PATH), read_only=True)
    except Exception:
        logger.debug("DuckDB unavailable, will fall back to JSONL", exc_info=True)
        return None


def _display_critical_path(plan_path: Path, json_mode: bool) -> None:
    """Compute and display critical path from the task graph.

    Loads the plan, extracts graph structure and duration hints,
    then computes and displays the critical path.

    Requirement: 43-REQ-2.2
    """
    try:
        from agent_fox.graph.critical_path import (
            compute_critical_path,
            format_critical_path,
        )
        from agent_fox.graph.persistence import load_plan

        graph = load_plan(plan_path)
        if graph is None:
            logger.info("No plan file found; skipping critical path output")
            return

        # Build node status dict, edges (predecessors), and duration hints
        nodes: dict[str, str] = {nid: node.status.value for nid, node in graph.nodes.items()}
        edges: dict[str, list[str]] = {nid: graph.predecessors(nid) for nid in graph.nodes}

        # Duration hints: removed along with prediction pipeline (89-REQ-6.1)
        duration_hints: dict[str, int] = {}

        result = compute_critical_path(nodes, edges, duration_hints)

        if json_mode:
            from agent_fox.cli.json_io import emit

            emit(
                {
                    "critical_path": {
                        "path": result.path,
                        "total_duration_ms": result.total_duration_ms,
                        "tied_paths": result.tied_paths,
                    }
                }
            )
        else:
            console = Console()
            console.print()
            console.print(format_critical_path(result))
    except Exception:
        logger.warning("Failed to compute critical path", exc_info=True)


@click.command("status")
@click.option("--model", is_flag=True, default=False, help="Include project model.")
@click.pass_context
@handle_agent_fox_errors
def status_cmd(ctx: click.Context, model: bool) -> None:
    """Show execution progress dashboard."""
    json_mode = ctx.obj.get("json", False)
    project_root = Path.cwd()
    agent_dir = project_root / AGENT_FOX_DIR
    plan_path = agent_dir / "plan.json"

    db_conn = _get_readonly_conn()
    try:
        report = _reporting_generate_status(plan_path=plan_path, db_conn=db_conn)
    finally:
        if db_conn is not None:
            db_conn.close()

    if json_mode:
        from agent_fox.cli.json_io import emit

        emit(asdict(report))
    else:
        console = Console()
        formatter = get_formatter(OutputFormat.TABLE, console=console)
        content = formatter.format_status(report)
        write_output(content, console=console)

    # Append project model and critical path when --model is requested
    if model:
        conn = _get_readonly_conn()
        if conn is not None:
            try:
                from agent_fox.knowledge.project_model import (
                    build_project_model,
                    format_project_model,
                )

                pm = build_project_model(conn)
                output = format_project_model(pm)
                if json_mode:
                    from agent_fox.cli.json_io import emit

                    emit({"project_model": asdict(pm)})
                else:
                    console = Console()
                    console.print()
                    console.print(output)
            finally:
                conn.close()
        else:
            logger.info("No DuckDB database found; skipping project model output")

        # Critical path computation from task graph
        _display_critical_path(plan_path, json_mode)
