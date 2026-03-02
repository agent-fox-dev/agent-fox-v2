"""CLI command for reset: agent-fox reset.

Reset failed/blocked tasks for retry, with optional single-task
reset and cascade unblocking.

Requirements: 07-REQ-4.3, 07-REQ-4.4, 07-REQ-5.3
"""

from __future__ import annotations

import logging
from pathlib import Path

import click

from agent_fox.core.errors import AgentFoxError
from agent_fox.engine.reset import ResetResult, reset_all, reset_task

logger = logging.getLogger(__name__)

_AGENT_FOX_DIR = ".agent-fox"


def _display_result(result: ResetResult) -> None:
    """Display a summary of the reset operation."""
    if not result.reset_tasks:
        if result.skipped_completed:
            click.echo(
                "Warning: Completed tasks cannot be reset.",
                err=True,
            )
        else:
            click.echo("Nothing to reset. All tasks are in a valid state.")
        return

    click.echo(f"Reset {len(result.reset_tasks)} task(s) to pending:")
    for task_id in result.reset_tasks:
        click.echo(f"  - {task_id}")

    if result.unblocked_tasks:
        click.echo(
            f"\nUnblocked {len(result.unblocked_tasks)} downstream task(s):",
        )
        for task_id in result.unblocked_tasks:
            click.echo(f"  - {task_id}")

    if result.cleaned_worktrees:
        click.echo(
            f"\nCleaned up {len(result.cleaned_worktrees)} worktree(s).",
        )

    if result.cleaned_branches:
        click.echo(
            f"Deleted {len(result.cleaned_branches)} branch(es).",
        )


@click.command("reset")
@click.argument("task_id", required=False, default=None)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def reset_cmd(ctx: click.Context, task_id: str | None, yes: bool) -> None:
    """Reset failed/blocked tasks for retry.

    If TASK_ID is provided, reset only that task.
    Otherwise, reset all incomplete tasks (with confirmation).
    """
    project_root = Path.cwd()
    agent_dir = project_root / _AGENT_FOX_DIR
    state_path = agent_dir / "state.jsonl"
    plan_path = agent_dir / "plan.json"
    worktrees_dir = agent_dir / "worktrees"

    if task_id is not None:
        # Single-task reset: no confirmation needed (07-REQ-5.3)
        try:
            result = reset_task(
                task_id=task_id,
                state_path=state_path,
                plan_path=plan_path,
                worktrees_dir=worktrees_dir,
                repo_path=project_root,
            )
        except AgentFoxError as exc:
            click.echo(f"Error: {exc}", err=True)
            ctx.exit(1)
            return

        _display_result(result)
    else:
        # Full reset: show tasks and prompt for confirmation (07-REQ-4.3)
        try:
            # First, load state to show what will be reset
            from agent_fox.engine.reset import (
                _RESETTABLE_STATUSES,
                _load_state_or_raise,
            )

            state = _load_state_or_raise(state_path)
        except AgentFoxError as exc:
            click.echo(f"Error: {exc}", err=True)
            ctx.exit(1)
            return

        # Find tasks that would be reset
        resettable = [
            (tid, status)
            for tid, status in state.node_states.items()
            if status in _RESETTABLE_STATUSES
        ]

        if not resettable:
            click.echo(
                "Nothing to reset. No failed, blocked, or in-progress tasks found.",
            )
            return

        click.echo("The following tasks will be reset to pending:")
        for tid, status in resettable:
            click.echo(f"  - {tid} ({status})")

        # Prompt for confirmation unless --yes (07-REQ-4.4)
        if not yes:
            if not click.confirm("\nProceed with reset?"):
                click.echo("Reset cancelled.")
                return

        try:
            result = reset_all(
                state_path=state_path,
                plan_path=plan_path,
                worktrees_dir=worktrees_dir,
                repo_path=project_root,
            )
        except AgentFoxError as exc:
            click.echo(f"Error: {exc}", err=True)
            ctx.exit(1)
            return

        _display_result(result)
