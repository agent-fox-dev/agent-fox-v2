"""CLI command for reset: agent-fox reset.

Reset failed/blocked tasks for retry, with optional single-task
reset and cascade unblocking. Supports --hard for comprehensive wipe.

Requirements: 07-REQ-4.3, 07-REQ-4.4, 07-REQ-5.3,
              35-REQ-2.1, 35-REQ-2.2, 35-REQ-5.1 .. 35-REQ-5.3,
              35-REQ-6.1, 35-REQ-6.2
"""

from __future__ import annotations

import logging
from pathlib import Path

import click

from agent_fox.core.errors import AgentFoxError
from agent_fox.engine.reset import (
    HardResetResult,
    ResetResult,
    hard_reset_all,
    hard_reset_task,
    reset_all,
    reset_task,
)

logger = logging.getLogger(__name__)

_AGENT_FOX_DIR = ".agent-fox"


def _result_to_dict(result: ResetResult) -> dict:
    """Convert a ResetResult to a JSON-serializable dict."""
    return {
        "reset_tasks": list(result.reset_tasks),
        "unblocked_tasks": list(result.unblocked_tasks),
        "cleaned_worktrees": list(result.cleaned_worktrees),
        "cleaned_branches": list(result.cleaned_branches),
        "skipped_completed": list(result.skipped_completed),
    }


def _hard_result_to_dict(result: HardResetResult) -> dict:
    """Convert a HardResetResult to a JSON-serializable dict."""
    return {
        "reset_tasks": list(result.reset_tasks),
        "cleaned_worktrees": list(result.cleaned_worktrees),
        "cleaned_branches": list(result.cleaned_branches),
        "compaction": {
            "original_count": result.compaction[0],
            "surviving_count": result.compaction[1],
        },
        "rollback": {
            "target_sha": result.rollback_sha,
            "skipped": result.rollback_sha is None,
        },
    }


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


def _display_hard_result(result: HardResetResult) -> None:
    """Display a human-readable summary of a hard reset operation."""
    count = len(result.reset_tasks)
    click.echo(f"Hard reset complete: {count} task(s) reset to pending.")

    if result.reset_tasks:
        for task_id in result.reset_tasks:
            click.echo(f"  - {task_id}")

    if result.cleaned_worktrees:
        click.echo(
            f"\nCleaned up {len(result.cleaned_worktrees)} worktree(s).",
        )

    if result.cleaned_branches:
        click.echo(
            f"Deleted {len(result.cleaned_branches)} branch(es).",
        )

    orig, surviving = result.compaction
    click.echo(f"\nKnowledge compaction: {orig} -> {surviving} facts.")

    if result.rollback_sha:
        click.echo(f"Code rolled back to {result.rollback_sha}.")
    else:
        click.echo("Code rollback skipped (no tracked commits).")


@click.command("reset")
@click.argument("task_id", required=False, default=None)
@click.option("--hard", is_flag=True, help="Full state wipe including completed tasks")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def reset_cmd(
    ctx: click.Context,
    task_id: str | None,
    hard: bool,
    yes: bool,
) -> None:
    """Reset failed/blocked tasks for retry.

    If TASK_ID is provided, reset only that task.
    Otherwise, reset all incomplete tasks (with confirmation).

    With --hard, perform a comprehensive wipe: reset ALL tasks (including
    completed), clean worktrees/branches, compact knowledge, and optionally
    roll back code on develop.
    """
    json_mode = (ctx.obj or {}).get("json", False)
    project_root = Path.cwd()
    agent_dir = project_root / _AGENT_FOX_DIR
    state_path = agent_dir / "state.jsonl"
    plan_path = agent_dir / "plan.json"
    worktrees_dir = agent_dir / "worktrees"
    memory_path = agent_dir / "memory.jsonl"

    if hard:
        _handle_hard_reset(
            ctx,
            task_id,
            yes,
            json_mode,
            state_path,
            plan_path,
            worktrees_dir,
            project_root,
            memory_path,
        )
    elif task_id is not None:
        _handle_soft_task_reset(
            ctx,
            task_id,
            json_mode,
            state_path,
            plan_path,
            worktrees_dir,
            project_root,
        )
    else:
        _handle_soft_reset_all(
            ctx,
            yes,
            json_mode,
            state_path,
            plan_path,
            worktrees_dir,
            project_root,
        )


def _handle_hard_reset(
    ctx: click.Context,
    task_id: str | None,
    yes: bool,
    json_mode: bool,
    state_path: Path,
    plan_path: Path,
    worktrees_dir: Path,
    project_root: Path,
    memory_path: Path,
) -> None:
    """Handle --hard reset (full or partial)."""
    # Confirmation: skip if --yes or --json (35-REQ-5.2, 35-REQ-5.3)
    if not json_mode and not yes:
        if task_id:
            msg = f"Hard reset task {task_id} (rolls back code, resets affected tasks)?"
        else:
            msg = "Hard reset ALL tasks (rolls back code, wipes all state)?"
        if not click.confirm(msg):
            click.echo("Hard reset cancelled.")
            return

    try:
        if task_id is not None:
            result = hard_reset_task(
                task_id=task_id,
                state_path=state_path,
                plan_path=plan_path,
                worktrees_dir=worktrees_dir,
                repo_path=project_root,
                memory_path=memory_path,
            )
        else:
            result = hard_reset_all(
                state_path=state_path,
                plan_path=plan_path,
                worktrees_dir=worktrees_dir,
                repo_path=project_root,
                memory_path=memory_path,
            )
    except AgentFoxError as exc:
        if json_mode:
            from agent_fox.cli.json_io import emit_error

            emit_error(str(exc))
            ctx.exit(1)
            return
        click.echo(f"Error: {exc}", err=True)
        ctx.exit(1)
        return

    if json_mode:
        from agent_fox.cli.json_io import emit

        emit(_hard_result_to_dict(result))
    else:
        _display_hard_result(result)


def _handle_soft_task_reset(
    ctx: click.Context,
    task_id: str,
    json_mode: bool,
    state_path: Path,
    plan_path: Path,
    worktrees_dir: Path,
    project_root: Path,
) -> None:
    """Handle single-task soft reset."""
    try:
        result = reset_task(
            task_id=task_id,
            state_path=state_path,
            plan_path=plan_path,
            worktrees_dir=worktrees_dir,
            repo_path=project_root,
        )
    except AgentFoxError as exc:
        if json_mode:
            from agent_fox.cli.json_io import emit_error

            emit_error(str(exc))
            ctx.exit(1)
            return
        click.echo(f"Error: {exc}", err=True)
        ctx.exit(1)
        return

    if json_mode:
        from agent_fox.cli.json_io import emit

        emit(_result_to_dict(result))
    else:
        _display_result(result)


def _handle_soft_reset_all(
    ctx: click.Context,
    yes: bool,
    json_mode: bool,
    state_path: Path,
    plan_path: Path,
    worktrees_dir: Path,
    project_root: Path,
) -> None:
    """Handle full soft reset (existing behavior)."""
    try:
        from agent_fox.engine.reset import (
            _RESETTABLE_STATUSES,
            _load_state_or_raise,
        )

        state = _load_state_or_raise(state_path)
    except AgentFoxError as exc:
        if json_mode:
            from agent_fox.cli.json_io import emit_error

            emit_error(str(exc))
            ctx.exit(1)
            return
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
        if json_mode:
            from agent_fox.cli.json_io import emit

            emit(
                _result_to_dict(
                    ResetResult(
                        reset_tasks=[],
                        unblocked_tasks=[],
                        cleaned_worktrees=[],
                        cleaned_branches=[],
                    )
                )
            )
            return
        click.echo(
            "Nothing to reset. No failed, blocked, or in-progress tasks found.",
        )
        return

    if not json_mode:
        click.echo("The following tasks will be reset to pending:")
        for tid, status in resettable:
            click.echo(f"  - {tid} ({status})")

    # Prompt for confirmation unless --yes (07-REQ-4.4)
    # In JSON mode, skip confirmation (non-interactive)
    if not json_mode and not yes:
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
        if json_mode:
            from agent_fox.cli.json_io import emit_error

            emit_error(str(exc))
            ctx.exit(1)
            return
        click.echo(f"Error: {exc}", err=True)
        ctx.exit(1)
        return

    if json_mode:
        from agent_fox.cli.json_io import emit

        emit(_result_to_dict(result))
    else:
        _display_result(result)
