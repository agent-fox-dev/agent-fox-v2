"""Reset engine: clear failed/blocked tasks, cascade unblock.

Requirements: 07-REQ-4.1, 07-REQ-4.2, 07-REQ-5.1, 07-REQ-5.2
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResetResult:
    """Result of a reset operation."""

    reset_tasks: list[str]  # task IDs that were reset
    unblocked_tasks: list[str]  # task IDs that were cascade-unblocked
    cleaned_worktrees: list[str]  # worktree directories removed
    cleaned_branches: list[str]  # git branches deleted


def reset_all(
    state_path: Path,
    plan_path: Path,
    worktrees_dir: Path,
    repo_path: Path,
) -> ResetResult:
    """Reset all incomplete tasks to pending.

    Resets tasks with status failed, blocked, or in_progress.
    Cleans up worktree directories and feature branches.

    Args:
        state_path: Path to .agent-fox/state.jsonl.
        plan_path: Path to .agent-fox/plan.json.
        worktrees_dir: Path to .agent-fox/worktrees/.
        repo_path: Path to the git repository root.

    Returns:
        ResetResult summarizing what was reset.

    Raises:
        AgentFoxError: If state or plan files are missing.
    """
    raise NotImplementedError


def reset_task(
    task_id: str,
    state_path: Path,
    plan_path: Path,
    worktrees_dir: Path,
    repo_path: Path,
) -> ResetResult:
    """Reset a single task and re-evaluate downstream blockers.

    If the reset task was the sole blocker for a downstream task,
    that downstream task is also reset to pending.

    Args:
        task_id: The task identifier to reset.
        state_path: Path to .agent-fox/state.jsonl.
        plan_path: Path to .agent-fox/plan.json.
        worktrees_dir: Path to .agent-fox/worktrees/.
        repo_path: Path to the git repository root.

    Returns:
        ResetResult summarizing what was reset and unblocked.

    Raises:
        AgentFoxError: If the task ID is not found in the plan.
        AgentFoxError: If the task is already completed.
    """
    raise NotImplementedError


def _clean_worktree(worktrees_dir: Path, task_id: str) -> str | None:
    """Remove a task's worktree directory if it exists.

    Args:
        worktrees_dir: Path to .agent-fox/worktrees/.
        task_id: The task identifier.

    Returns:
        The worktree path that was removed, or None if it didn't exist.
    """
    raise NotImplementedError


def _clean_branch(repo_path: Path, task_id: str) -> str | None:
    """Delete a task's feature branch if it exists.

    The branch name is derived from the task ID:
    feature/{spec_name}-{group_number}.

    Args:
        repo_path: Path to the git repository root.
        task_id: The task identifier.

    Returns:
        The branch name that was deleted, or None if it didn't exist.
    """
    raise NotImplementedError


def _find_sole_blocker_dependents(
    task_id: str,
    plan: object,
    state: object,
) -> list[str]:
    """Find downstream tasks where task_id is the sole blocker.

    A downstream task qualifies if:
    1. Its status is 'blocked'.
    2. All of its prerequisites are either 'completed' or the task
       being reset.

    Args:
        task_id: The task being reset.
        plan: The task graph.
        state: Current execution state.

    Returns:
        List of task IDs that can be unblocked.
    """
    raise NotImplementedError
