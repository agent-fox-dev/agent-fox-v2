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
from typing import TYPE_CHECKING

import click

from agent_fox.core.paths import AGENT_FOX_DIR, DEFAULT_DB_PATH
from agent_fox.engine.reset import (
    HardResetResult,
    ResetResult,
    hard_reset_all,
    hard_reset_task,
    reset_all,
    reset_spec,
    reset_task,
)

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)


def _get_db_conn() -> duckdb.DuckDBPyConnection | None:
    """Open a read-write DuckDB connection for reset operations.

    Returns None if the database does not exist or cannot be opened.

    Requirements: 105-REQ-5.3 (DB-only state persistence)
    """
    try:
        import duckdb

        if not DEFAULT_DB_PATH.exists():
            return None
        return duckdb.connect(str(DEFAULT_DB_PATH))
    except Exception:
        logger.debug("DuckDB unavailable for reset", exc_info=True)
        return None


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


def _spec_result_to_dict(result: ResetResult) -> dict:
    """Convert a spec-reset ResetResult to a JSON-serializable dict.

    Uses the keys required by 50-REQ-3.4: reset_tasks,
    cleaned_worktrees, cleaned_branches.
    """
    return {
        "reset_tasks": list(result.reset_tasks),
        "cleaned_worktrees": list(result.cleaned_worktrees),
        "cleaned_branches": list(result.cleaned_branches),
    }


def _display_spec_result(result: ResetResult, spec_name: str) -> None:
    """Display a human-readable summary of a spec-scoped reset.

    Requirement: 50-REQ-3.5
    """
    if not result.reset_tasks:
        click.echo(
            f"Nothing to reset. All tasks for spec '{spec_name}' are already pending.",
        )
        return

    click.echo(f"Reset {len(result.reset_tasks)} task(s) for spec '{spec_name}':")
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


@click.command("reset")
@click.argument("task_id", required=False, default=None)
@click.option("--hard", is_flag=True, help="Full state wipe including completed tasks")
@click.option(
    "--spec",
    "filter_spec",
    default=None,
    help="Reset all tasks for a single spec",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def reset_cmd(
    ctx: click.Context,
    task_id: str | None,
    hard: bool,
    filter_spec: str | None,
    yes: bool,
) -> None:
    """Reset failed/blocked tasks for retry.

    If TASK_ID is provided, reset only that task.
    Otherwise, reset all incomplete tasks (with confirmation).

    With --hard, perform a comprehensive wipe: reset ALL tasks (including
    completed), clean worktrees/branches, compact knowledge, and optionally
    roll back code on develop.

    With --spec, reset all tasks belonging to a single spec.
    """
    json_mode = (ctx.obj or {}).get("json", False)
    project_root = Path.cwd()
    agent_dir = project_root / AGENT_FOX_DIR
    plan_path = agent_dir / "plan.json"
    worktrees_dir = agent_dir / "worktrees"
    memory_path = agent_dir / "memory.jsonl"

    # Mutual exclusivity checks (50-REQ-2.1, 50-REQ-2.2)
    if filter_spec is not None:
        if hard:
            click.echo(
                "Error: --spec and --hard are mutually exclusive.",
                err=True,
            )
            ctx.exit(1)
            return
        if task_id is not None:
            click.echo(
                "Error: --spec and TASK_ID are mutually exclusive.",
                err=True,
            )
            ctx.exit(1)
            return

    db_conn = _get_db_conn()
    try:
        if filter_spec is not None:
            _handle_spec_reset(
                ctx,
                filter_spec,
                yes,
                json_mode,
                db_conn,
                plan_path,
                worktrees_dir,
                project_root,
            )
        elif hard:
            _handle_hard_reset(
                ctx,
                task_id,
                yes,
                json_mode,
                db_conn,
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
                db_conn,
                plan_path,
                worktrees_dir,
                project_root,
            )
        else:
            _handle_soft_reset_all(
                ctx,
                yes,
                json_mode,
                db_conn,
                plan_path,
                worktrees_dir,
                project_root,
            )
    finally:
        if db_conn is not None:
            db_conn.close()


def _handle_spec_reset(
    ctx: click.Context,
    spec_name: str,
    yes: bool,
    json_mode: bool,
    db_conn: duckdb.DuckDBPyConnection | None,
    plan_path: Path,
    worktrees_dir: Path,
    project_root: Path,
) -> None:
    """Handle --spec reset (spec-scoped).

    Requirements: 50-REQ-1.1 .. 50-REQ-1.8, 50-REQ-3.1 .. 50-REQ-3.5,
                  50-REQ-4.1, 50-REQ-4.2
    """
    # Confirmation: skip if --yes or --json (50-REQ-3.1, 50-REQ-3.3, 50-REQ-3.4)
    if not json_mode and not yes:
        msg = f"Reset all tasks for spec '{spec_name}'?"
        if not click.confirm(msg):
            click.echo("Reset cancelled.")
            return

    result = reset_spec(
        spec_name=spec_name,
        plan_path=plan_path,
        worktrees_dir=worktrees_dir,
        repo_path=project_root,
        db_conn=db_conn,
    )

    if json_mode:
        from agent_fox.cli.json_io import emit

        emit(_spec_result_to_dict(result))
    else:
        _display_spec_result(result, spec_name)


def _handle_hard_reset(
    ctx: click.Context,
    task_id: str | None,
    yes: bool,
    json_mode: bool,
    db_conn: duckdb.DuckDBPyConnection | None,
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

    if task_id is not None:
        result = hard_reset_task(
            task_id=task_id,
            plan_path=plan_path,
            worktrees_dir=worktrees_dir,
            repo_path=project_root,
            memory_path=memory_path,
            db_conn=db_conn,
        )
    else:
        result = hard_reset_all(
            plan_path=plan_path,
            worktrees_dir=worktrees_dir,
            repo_path=project_root,
            memory_path=memory_path,
            db_conn=db_conn,
        )

    if json_mode:
        from agent_fox.cli.json_io import emit

        emit(_hard_result_to_dict(result))
    else:
        _display_hard_result(result)


def _handle_soft_task_reset(
    ctx: click.Context,
    task_id: str,
    json_mode: bool,
    db_conn: duckdb.DuckDBPyConnection | None,
    plan_path: Path,
    worktrees_dir: Path,
    project_root: Path,
) -> None:
    """Handle single-task soft reset."""
    result = reset_task(
        task_id=task_id,
        plan_path=plan_path,
        worktrees_dir=worktrees_dir,
        repo_path=project_root,
        db_conn=db_conn,
    )

    if json_mode:
        from agent_fox.cli.json_io import emit

        emit(_result_to_dict(result))
    else:
        _display_result(result)


def _handle_soft_reset_all(
    ctx: click.Context,
    yes: bool,
    json_mode: bool,
    db_conn: duckdb.DuckDBPyConnection | None,
    plan_path: Path,
    worktrees_dir: Path,
    project_root: Path,
) -> None:
    """Handle full soft reset (existing behavior)."""
    from agent_fox.engine.reset import (
        _RESETTABLE_STATUSES,
        _load_state_or_raise,
    )

    state = _load_state_or_raise(db_conn)

    # Find tasks that would be reset
    resettable = [(tid, status) for tid, status in state.node_states.items() if status in _RESETTABLE_STATUSES]

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

    result = reset_all(
        plan_path=plan_path,
        worktrees_dir=worktrees_dir,
        repo_path=project_root,
        db_conn=db_conn,
    )

    if json_mode:
        from agent_fox.cli.json_io import emit

        emit(_result_to_dict(result))
    else:
        _display_result(result)
