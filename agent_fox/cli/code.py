"""CLI code command: execute the task plan via the orchestrator.

Thin CLI wrapper that connects the Click command group to the
orchestrator engine. Reads configuration, applies CLI overrides,
constructs the orchestrator, runs execution, prints a summary,
and exits with a meaningful code.

Requirements: 16-REQ-1.1 through 16-REQ-5.2, 23-REQ-5.1, 23-REQ-5.E1
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

from agent_fox.cli import json_io
from agent_fox.core.config import AgentFoxConfig, HookConfig, OrchestratorConfig
from agent_fox.core.errors import AgentFoxError
from agent_fox.engine.engine import Orchestrator
from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.engine.state import ExecutionState
from agent_fox.knowledge.db import KnowledgeDB, open_knowledge_store
from agent_fox.knowledge.duckdb_sink import DuckDBSink
from agent_fox.knowledge.ingest import run_background_ingestion
from agent_fox.knowledge.sink import SinkDispatcher
from agent_fox.reporting.formatters import format_tokens
from agent_fox.ui.progress import ProgressDisplay
from agent_fox.ui.theme import create_theme

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


def _apply_overrides(
    config: OrchestratorConfig,
    parallel: int | None,
    max_cost: float | None,
    max_sessions: int | None,
) -> OrchestratorConfig:
    """Return a new OrchestratorConfig with CLI overrides applied.

    Only overrides fields that were explicitly provided (not None).
    All non-overridden fields are preserved from the original config.

    Requirements: 16-REQ-2.1, 16-REQ-2.3, 16-REQ-2.4, 16-REQ-2.5
    """
    overrides: dict[str, object] = {}
    if parallel is not None:
        overrides["parallel"] = parallel
    if max_cost is not None:
        overrides["max_cost"] = max_cost
    if max_sessions is not None:
        overrides["max_sessions"] = max_sessions
    if overrides:
        merged = config.model_dump()
        merged.update(overrides)
        return OrchestratorConfig.model_validate(merged)
    return config


def _count_by_status(node_states: dict[str, str]) -> dict[str, int]:
    """Count tasks grouped by their status value."""
    counts: dict[str, int] = {}
    for status in node_states.values():
        counts[status] = counts.get(status, 0) + 1
    return counts


def _print_summary(state: ExecutionState) -> None:
    """Print a compact execution summary.

    Displays task counts, token usage, cost, and run status in the
    same compact text style used by ``agent-fox status``.

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
    click.echo(
        f"Tokens: {format_tokens(state.total_input_tokens)} in / "
        f"{format_tokens(state.total_output_tokens)} out"
    )
    click.echo(f"Cost:   ${state.total_cost:.2f}")
    click.echo(f"Status: {state.run_status}")


def _ingest_if_available(
    knowledge_db: KnowledgeDB | None,
    config: AgentFoxConfig,
) -> None:
    """Run background knowledge ingestion if the store is available."""
    if knowledge_db is None:
        return
    try:
        run_background_ingestion(
            knowledge_db.connection,
            config.knowledge,
            Path.cwd(),
        )
    except Exception:
        logger.warning("Background ingestion failed", exc_info=True)


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
@click.pass_context
def code_cmd(
    ctx: click.Context,
    parallel: int | None,
    no_hooks: bool,
    max_cost: float | None,
    max_sessions: int | None,
    debug: bool,
) -> None:
    """Execute the task plan."""
    # 16-REQ-1.2: load config from Click context
    config = ctx.obj["config"]
    quiet: bool = ctx.obj.get("quiet", False)
    json_mode: bool = ctx.obj.get("json", False)

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
    plan_path = Path(".agent-fox/plan.json")
    if not plan_path.exists():
        if json_mode:
            json_io.emit_error(
                "Plan file not found. "
                "Run `agent-fox plan` first to generate a plan."
            )
            sys.exit(1)
        click.echo(
            "Error: Plan file not found. "
            "Run `agent-fox plan` first to generate a plan.",
            err=True,
        )
        sys.exit(1)

    state_path = Path(".agent-fox/state.jsonl")

    # 16-REQ-2.5: apply CLI overrides to OrchestratorConfig
    orch_config = _apply_overrides(
        config.orchestrator,
        parallel,
        max_cost,
        max_sessions,
    )

    # Session runner factory (16-REQ-5.1, 16-REQ-5.2)
    full_config: AgentFoxConfig = config
    hook_cfg: HookConfig | None = config.hooks

    # 11-REQ-4.2: Create DuckDB sink for session outcome recording
    # v2 three-layer model: session outcomes always, tool signals debug-only
    sink_dispatcher = SinkDispatcher()
    knowledge_db = open_knowledge_store(config.knowledge)
    if knowledge_db is not None:
        sink_dispatcher.add(DuckDBSink(knowledge_db.connection, debug=debug))

    # v2: attach JSONL audit sink when --debug is active
    if debug:
        from agent_fox.knowledge.jsonl_sink import JsonlSink

        jsonl_dir = Path(".agent-fox")
        sink_dispatcher.add(JsonlSink(jsonl_dir))

    # 12-REQ-4.1, 12-REQ-4.2: Ingest ADRs and git commits at startup
    _ingest_if_available(knowledge_db, config)

    # 18-REQ-5.1: Create progress display (suppressed in JSON mode)
    theme = create_theme(config.theme)
    progress = ProgressDisplay(theme, quiet=quiet or json_mode)

    def session_runner_factory(node_id: str) -> NodeSessionRunner:
        """Create a session runner for the given node.

        Parses the node_id to extract spec_name and task_group, then
        returns a runner configured with the project's AgentFoxConfig,
        hook config, and task-specific prompts.

        16-REQ-5.E1: If construction fails, the runner's execute()
        method will catch and report the failure as a session error.
        """
        return NodeSessionRunner(
            node_id,
            full_config,
            hook_config=hook_cfg,
            no_hooks=no_hooks,
            sink_dispatcher=sink_dispatcher,
            knowledge_db=knowledge_db,
            activity_callback=progress.activity_callback,
        )

    # 18-REQ-5.1, 18-REQ-5.E1: Wrap execution with progress start/stop
    progress.start()
    try:
        # 16-REQ-1.3: construct Orchestrator
        orchestrator = Orchestrator(
            orch_config,
            plan_path=plan_path,
            state_path=state_path,
            session_runner_factory=session_runner_factory,
            hook_config=config.hooks,
            specs_dir=Path(".specs"),
            no_hooks=no_hooks,
            task_callback=progress.task_callback,
            barrier_callback=lambda: _ingest_if_available(knowledge_db, config),
        )

        # 16-REQ-1.4: execute via asyncio.run()
        state: ExecutionState = asyncio.run(orchestrator.run())

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
        # 12-REQ-4.1, 12-REQ-4.2: Re-ingest to capture new commits/ADRs
        _ingest_if_available(knowledge_db, config)
        # Clean up knowledge store connection
        sink_dispatcher.close()
        if knowledge_db is not None:
            knowledge_db.close()

    # 23-REQ-5.1: emit JSONL summary in JSON mode
    if json_mode:
        counts = _count_by_status(state.node_states)
        json_io.emit_line({
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
        })
    else:
        # 16-REQ-3.1: print summary
        _print_summary(state)

    # 16-REQ-4.*: exit with appropriate code
    exit_code = _exit_code_for_status(state.run_status)
    if exit_code != 0:
        sys.exit(exit_code)
