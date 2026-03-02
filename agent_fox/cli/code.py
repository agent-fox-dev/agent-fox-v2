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
from datetime import UTC, datetime
from pathlib import Path

import click

from agent_fox.core.config import AgentFoxConfig, OrchestratorConfig
from agent_fox.core.errors import AgentFoxError
from agent_fox.core.models import calculate_cost, resolve_model
from agent_fox.engine.orchestrator import Orchestrator
from agent_fox.engine.state import ExecutionState, SessionRecord
from agent_fox.reporting.formatters import _format_tokens
from agent_fox.session.context import assemble_context
from agent_fox.session.prompt import build_system_prompt, build_task_prompt
from agent_fox.session.runner import run_session
from agent_fox.workspace.worktree import create_worktree

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


class _NodeSessionRunner:
    """Session runner for a single task graph node.

    Created by the session_runner_factory closure. Handles workspace
    creation, context assembly, prompt building, session execution,
    and result conversion to SessionRecord.

    Requirements: 16-REQ-5.1, 16-REQ-5.E1
    """

    def __init__(self, node_id: str, config: AgentFoxConfig) -> None:
        self._node_id = node_id
        self._config = config
        # Parse node_id format: "{spec_name}:{group_number}"
        parts = node_id.rsplit(":", 1)
        self._spec_name = parts[0]
        self._task_group = int(parts[1])

    async def execute(
        self,
        node_id: str,
        attempt: int,
        previous_error: str | None = None,
    ) -> SessionRecord:
        """Execute a coding session and return a SessionRecord.

        Creates an isolated worktree, assembles context from spec files,
        builds system/task prompts, runs the session via claude-code-sdk,
        and converts the outcome to a SessionRecord with cost calculation.

        16-REQ-5.E1: Catches all exceptions and returns a failed
        SessionRecord so the orchestrator can apply retry logic.
        """
        try:
            repo_root = Path.cwd()

            # Create isolated worktree
            workspace = await create_worktree(
                repo_root,
                self._spec_name,
                self._task_group,
            )

            # Assemble context from spec documents
            spec_dir = repo_root / ".specs" / self._spec_name
            context = assemble_context(spec_dir, self._task_group)

            # Build prompts
            system_prompt = build_system_prompt(
                context=context,
                task_group=self._task_group,
                spec_name=self._spec_name,
            )
            task_prompt = build_task_prompt(
                task_group=self._task_group,
                spec_name=self._spec_name,
            )

            # Inject retry context into task prompt
            if previous_error and attempt > 1:
                task_prompt = (
                    f"{task_prompt}\n\n"
                    f"**Note:** This is retry attempt {attempt}. "
                    f"The previous attempt failed with:\n"
                    f"```\n{previous_error}\n```\n"
                    f"Please address this error.\n"
                )

            # Execute session
            outcome = await run_session(
                workspace=workspace,
                node_id=node_id,
                system_prompt=system_prompt,
                task_prompt=task_prompt,
                config=self._config,
            )

            # Calculate cost from token usage
            model_entry = resolve_model(self._config.models.coding)
            cost = calculate_cost(
                outcome.input_tokens,
                outcome.output_tokens,
                model_entry,
            )

            return SessionRecord(
                node_id=node_id,
                attempt=attempt,
                status=outcome.status,
                input_tokens=outcome.input_tokens,
                output_tokens=outcome.output_tokens,
                cost=cost,
                duration_ms=outcome.duration_ms,
                error_message=outcome.error_message,
                timestamp=datetime.now(UTC).isoformat(),
            )

        except Exception as exc:
            logger.error(
                "Session runner failed for %s (attempt %d): %s",
                node_id,
                attempt,
                exc,
            )
            return SessionRecord(
                node_id=node_id,
                attempt=attempt,
                status="failed",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                duration_ms=0,
                error_message=str(exc),
                timestamp=datetime.now(UTC).isoformat(),
            )


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
    full_config: AgentFoxConfig = config

    def session_runner_factory(node_id: str) -> _NodeSessionRunner:
        """Create a session runner for the given node.

        Parses the node_id to extract spec_name and task_group, then
        returns a runner configured with the project's AgentFoxConfig,
        workspace info, and task-specific prompts.

        16-REQ-5.E1: If construction fails, the runner's execute()
        method will catch and report the failure as a session error.
        """
        return _NodeSessionRunner(node_id, full_config)

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
