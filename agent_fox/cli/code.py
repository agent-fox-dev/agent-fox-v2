"""CLI code command: execute the task plan via the orchestrator.

Thin CLI wrapper that delegates to ``engine.run.run_code()`` for
orchestrator execution, then handles output formatting and exit codes.

Requirements: 16-REQ-1.1 through 16-REQ-5.2, 23-REQ-5.1, 23-REQ-5.E1
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

from agent_fox.cli import json_io
from agent_fox.core.errors import AgentFoxError
from agent_fox.core.paths import PLAN_PATH
from agent_fox.engine.run import InterruptedResult, run_code
from agent_fox.engine.state import ExecutionState
from agent_fox.reporting.formatters import format_tokens

logger = logging.getLogger(__name__)

# Exit code mapping: run_status -> shell exit code
# 16-REQ-4.1 through 16-REQ-4.5, 16-REQ-4.E1
_EXIT_CODES: dict[str, int] = {
    "completed": 0,
    "stalled": 2,
    "cost_limit": 3,
    "session_limit": 3,
    "interrupted": 130,
}


def _exit_code_for_status(run_status: str) -> int:
    """Map a run status string to a shell exit code.

    Returns the documented exit code for known statuses, or 1 for
    any unrecognized status.

    Requirements: 16-REQ-4.1 through 16-REQ-4.5, 16-REQ-4.E1
    """
    return _EXIT_CODES.get(run_status, 1)


def _count_by_status(node_states: dict[str, str]) -> dict[str, int]:
    """Count tasks grouped by their status value."""
    counts: dict[str, int] = {}
    for status in node_states.values():
        counts[status] = counts.get(status, 0) + 1
    return counts


def _print_summary(state: ExecutionState) -> None:
    """Print a compact execution summary.

    Requirements: 16-REQ-3.1, 16-REQ-3.2, 16-REQ-3.E1
    """
    total = len(state.node_states)

    # 16-REQ-3.E1: empty plan
    if total == 0:
        click.echo("No tasks to execute.")
        return

    counts = _count_by_status(state.node_states)
    done = counts.get("completed", 0)
    in_progress = counts.get("in_progress", 0)
    pending = counts.get("pending", 0)
    failed = counts.get("failed", 0)
    blocked = counts.get("blocked", 0)

    parts = [f"{done}/{total} done"]
    if in_progress:
        parts.append(f"{in_progress} in progress")
    if pending:
        parts.append(f"{pending} pending")
    if failed:
        parts.append(f"{failed} failed")
    if blocked:
        parts.append(f"{blocked} blocked")

    click.echo(f"Tasks:  {', '.join(parts)}")
    click.echo(f"Tokens: {format_tokens(state.total_input_tokens)} in / {format_tokens(state.total_output_tokens)} out")
    click.echo(f"Cost:   ${state.total_cost:.2f}")
    click.echo(f"Status: {state.run_status}")


def _run_review_only_mode(
    config: object,
    specs_dir_override: str | None,
) -> None:
    """Execute review-only mode: run review archetypes without coder sessions.

    Requirements: 53-REQ-6.1, 53-REQ-6.3, 53-REQ-6.5, 53-REQ-6.E1
    """
    from agent_fox.graph.injection import (
        build_review_only_graph,
        run_review_only,
    )
    from agent_fox.knowledge.db import open_knowledge_store
    from agent_fox.knowledge.duckdb_sink import DuckDBSink
    from agent_fox.knowledge.sink import SinkDispatcher

    specs_path = Path(specs_dir_override) if specs_dir_override else Path(".specs")

    graph = build_review_only_graph(specs_path, config.archetypes)

    if not graph.nodes:
        click.echo("No specs eligible for review")
        return

    sink_dispatcher = SinkDispatcher()
    knowledge_db = open_knowledge_store(config.knowledge)
    sink_dispatcher.add(DuckDBSink(knowledge_db.connection))

    try:
        run_review_only(specs_path, config.archetypes, sink=sink_dispatcher)

        from agent_fox.graph.injection import print_review_only_summary

        print_review_only_summary(knowledge_db.connection)
    finally:
        sink_dispatcher.close()
        knowledge_db.close()


@click.command("code")
@click.option(
    "--parallel",
    type=int,
    default=None,
    help="Override parallelism (1-8)",
)
@click.option(
    "--no-hooks",
    is_flag=True,
    default=False,
    help="Skip all hook scripts",
)
@click.option(
    "--max-cost",
    type=float,
    default=None,
    help="Cost ceiling in USD",
)
@click.option(
    "--max-sessions",
    type=int,
    default=None,
    help="Session count limit",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug audit trail (JSONL + DuckDB tool signals)",
)
@click.option(
    "--review-only",
    is_flag=True,
    default=False,
    help="Run only review archetypes (Skeptic, Verifier, Oracle), skip coder sessions",
)
@click.option(
    "--specs-dir",
    type=click.Path(),
    default=None,
    help="Path to specs directory (default: .specs)",
)
@click.option(
    "--watch",
    is_flag=True,
    default=False,
    help="Keep running and poll for new specs after all tasks complete",
)
@click.option(
    "--watch-interval",
    type=int,
    default=None,
    help="Seconds between watch polls (default: 60, minimum: 10)",
)
@click.pass_context
def code_cmd(
    ctx: click.Context,
    parallel: int | None,
    no_hooks: bool,
    max_cost: float | None,
    max_sessions: int | None,
    debug: bool,
    review_only: bool,
    specs_dir: str | None,
    watch: bool,
    watch_interval: int | None,
) -> None:
    """Execute the task plan."""
    # 16-REQ-1.2: load config from Click context
    config = ctx.obj["config"]
    quiet: bool = ctx.obj.get("quiet", False)
    json_mode: bool = ctx.obj.get("json", False)

    # 53-REQ-6.1: review-only mode — skip coder sessions, run review archetypes only
    if review_only:
        _run_review_only_mode(config, specs_dir)
        return

    # 23-REQ-7.1: read stdin JSON when in JSON mode
    if json_mode:
        stdin_data = json_io.read_stdin()
        if parallel is None and "parallel" in stdin_data:
            parallel = int(stdin_data["parallel"])
        if max_cost is None and "max_cost" in stdin_data:
            max_cost = float(stdin_data["max_cost"])
        if max_sessions is None and "max_sessions" in stdin_data:
            max_sessions = int(stdin_data["max_sessions"])

    # 16-REQ-1.E1: check plan file exists
    plan_path = PLAN_PATH
    if not plan_path.exists():
        if json_mode:
            json_io.emit_error("Plan file not found. Run `agent-fox plan` first to generate a plan.")
            sys.exit(1)
        click.echo(
            "Error: Plan file not found. Run `agent-fox plan` first to generate a plan.",
            err=True,
        )
        sys.exit(1)

    # 18-REQ-5.1: Create progress display (suppressed in JSON mode)
    from agent_fox.ui.display import create_theme
    from agent_fox.ui.progress import ProgressDisplay

    theme = create_theme(config.theme)
    progress = ProgressDisplay(theme, quiet=quiet or json_mode)

    progress.start()
    try:
        result = asyncio.run(
            run_code(
                config,
                parallel=parallel,
                no_hooks=no_hooks,
                max_cost=max_cost,
                max_sessions=max_sessions,
                debug=debug,
                watch=watch,
                watch_interval=watch_interval,
                specs_dir=Path(specs_dir) if specs_dir else None,
                activity_callback=progress.activity_callback,
                task_callback=progress.task_callback,
            )
        )
    except KeyboardInterrupt:
        # 23-REQ-5.E1: emit interrupted status in JSON mode
        if json_mode:
            json_io.emit_line({"status": "interrupted"})
        sys.exit(130)
    except AgentFoxError as exc:
        logger.debug("Execution failed", exc_info=True)
        if json_mode:
            json_io.emit_error(str(exc))
            sys.exit(1)
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        # 16-REQ-1.E2: unexpected exceptions
        logger.debug("Unexpected error during execution", exc_info=True)
        if json_mode:
            json_io.emit_error(str(exc))
            sys.exit(1)
        click.echo(f"Error: unexpected error: {exc}", err=True)
        sys.exit(1)
    finally:
        progress.stop()

    # Handle interrupted result from run_code
    if isinstance(result, InterruptedResult):
        if json_mode:
            json_io.emit_line({"status": "interrupted"})
        sys.exit(130)

    state: ExecutionState = result

    # 23-REQ-5.1: emit JSONL summary in JSON mode
    if json_mode:
        counts = _count_by_status(state.node_states)
        json_io.emit_line(
            {
                "event": "complete",
                "summary": {
                    "tasks": len(state.node_states),
                    "completed": counts.get("completed", 0),
                    "failed": counts.get("failed", 0),
                    "input_tokens": state.total_input_tokens,
                    "output_tokens": state.total_output_tokens,
                    "cost": state.total_cost,
                    "run_status": state.run_status,
                },
            }
        )
    else:
        # 16-REQ-3.1: print summary
        _print_summary(state)

    # 16-REQ-4.*: exit with appropriate code
    exit_code = _exit_code_for_status(state.run_status)
    if exit_code != 0:
        sys.exit(exit_code)
