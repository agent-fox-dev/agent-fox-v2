"""CLI code command: execute the task plan via the orchestrator.

Thin CLI wrapper that connects the Click command group to the
orchestrator engine. Reads configuration, applies CLI overrides,
constructs the orchestrator, runs execution, prints a summary,
and exits with a meaningful code.

Requirements: 16-REQ-1.1 through 16-REQ-5.2
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

from agent_fox.core.config import OrchestratorConfig
from agent_fox.core.errors import AgentFoxError
from agent_fox.engine.orchestrator import Orchestrator
from agent_fox.engine.state import ExecutionState
from agent_fox.reporting.formatters import _format_tokens

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
        return config.model_copy(update=overrides)
    return config


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

    done = sum(1 for s in state.node_states.values() if s == "completed")
    in_progress = sum(1 for s in state.node_states.values() if s == "in_progress")
    pending = sum(1 for s in state.node_states.values() if s == "pending")
    failed = sum(1 for s in state.node_states.values() if s in ("failed", "blocked"))

    parts = [f"{done}/{total} done"]
    if in_progress:
        parts.append(f"{in_progress} in progress")
    if pending:
        parts.append(f"{pending} pending")
    if failed:
        parts.append(f"{failed} failed")

    click.echo(f"Tasks:  {', '.join(parts)}")
    click.echo(
        f"Tokens: {_format_tokens(state.total_input_tokens)} in / "
        f"{_format_tokens(state.total_output_tokens)} out"
    )
    click.echo(f"Cost:   ${state.total_cost:.2f}")
    click.echo(f"Status: {state.run_status}")


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
@click.pass_context
def code_cmd(
    ctx: click.Context,
    parallel: int | None,
    no_hooks: bool,
    max_cost: float | None,
    max_sessions: int | None,
) -> None:
    """Execute the task plan."""
    # 16-REQ-1.2: load config from Click context
    config = ctx.obj["config"]

    # 16-REQ-1.E1: check plan file exists
    plan_path = Path(".agent-fox/plan.json")
    if not plan_path.exists():
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
    def session_runner_factory(node_id: str) -> None:
        """Placeholder session runner factory.

        The actual runner is dispatched by the orchestrator's serial/parallel
        runner infrastructure. This factory is injected to satisfy the
        orchestrator's constructor contract.
        """

    try:
        # 16-REQ-1.3: construct Orchestrator
        orchestrator = Orchestrator(
            orch_config,
            plan_path=plan_path,
            state_path=state_path,
            session_runner_factory=session_runner_factory,
        )

        # 16-REQ-1.4: execute via asyncio.run()
        state: ExecutionState = asyncio.run(orchestrator.run())

    except AgentFoxError as exc:
        logger.debug("Execution failed", exc_info=True)
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        # 16-REQ-1.E2: unexpected exceptions
        logger.debug("Unexpected error during execution", exc_info=True)
        click.echo(f"Error: unexpected error: {exc}", err=True)
        sys.exit(1)

    # 16-REQ-3.1: print summary
    _print_summary(state)

    # 16-REQ-4.*: exit with appropriate code
    exit_code = _exit_code_for_status(state.run_status)
    if exit_code != 0:
        sys.exit(exit_code)
