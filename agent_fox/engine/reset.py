"""Reset engine: clear failed/blocked tasks, cascade unblock.

Requirements: 07-REQ-4.1, 07-REQ-4.2, 07-REQ-5.1, 07-REQ-5.2
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from agent_fox.core.errors import AgentFoxError
from agent_fox.engine.state import ExecutionState, StateManager
from agent_fox.graph.persistence import load_plan
from agent_fox.graph.types import TaskGraph

logger = logging.getLogger(__name__)

# Statuses that qualify for reset (not completed, pending, or skipped)
_RESETTABLE_STATUSES = frozenset({"failed", "blocked", "in_progress"})


@dataclass(frozen=True)
class ResetResult:
    """Result of a reset operation."""

    reset_tasks: list[str]  # task IDs that were reset
    unblocked_tasks: list[str]  # task IDs that were cascade-unblocked
    cleaned_worktrees: list[str]  # worktree directories removed
    cleaned_branches: list[str]  # git branches deleted
    skipped_completed: list[str] = field(
        default_factory=list,
    )  # completed tasks that could not be reset


def _load_or_raise[T](
    path: Path,
    loader: Callable[[Path], T | None],
    error_msg: str,
) -> T:
    """Load a resource from *path*, raising AgentFoxError if missing.

    Args:
        path: File to load.
        loader: Callable that returns None on failure.
        error_msg: Human-friendly message if loading fails.

    Raises:
        AgentFoxError: If *loader* returns None.
    """
    result = loader(path)
    if result is None:
        raise AgentFoxError(error_msg, path=str(path))
    return result


def _load_state_or_raise(state_path: Path) -> ExecutionState:
    """Load execution state from state.jsonl, raising if missing."""
    return _load_or_raise(
        state_path,
        lambda p: StateManager(p).load(),
        "No execution state found. Run `agent-fox code` first.",
    )


def _load_plan_or_raise(plan_path: Path) -> TaskGraph:
    """Load the task graph from plan.json, raising on failure."""
    return _load_or_raise(
        plan_path,
        load_plan,
        "No plan file found. Run `agent-fox plan` first.",
    )


def _task_id_to_worktree_path(worktrees_dir: Path, task_id: str) -> Path:
    """Convert a task ID to its worktree directory path.

    Task ID format: "spec_name:group_number"
    Worktree path: worktrees_dir / spec_name / group_number
    """
    parts = task_id.split(":")
    if len(parts) == 2:
        return worktrees_dir / parts[0] / parts[1]
    return worktrees_dir / task_id


def _task_id_to_branch_name(task_id: str) -> str:
    """Convert a task ID to its feature branch name.

    Task ID format: "spec_name:group_number"
    Branch name: "feature/spec_name-group_number"
    """
    parts = task_id.split(":")
    if len(parts) == 2:
        return f"feature/{parts[0]}-{parts[1]}"
    return f"feature/{task_id}"


def _clean_worktree(worktrees_dir: Path, task_id: str) -> str | None:
    """Remove a task's worktree directory if it exists.

    Args:
        worktrees_dir: Path to .agent-fox/worktrees/.
        task_id: The task identifier.

    Returns:
        The worktree path that was removed, or None if it didn't exist.
    """
    wt_path = _task_id_to_worktree_path(worktrees_dir, task_id)
    if wt_path.exists():
        try:
            shutil.rmtree(wt_path)
            logger.info("Removed worktree: %s", wt_path)
            return str(wt_path)
        except OSError as exc:
            logger.warning("Failed to remove worktree %s: %s", wt_path, exc)
    return None


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
    branch_name = _task_id_to_branch_name(task_id)
    try:
        result = subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info("Deleted branch: %s", branch_name)
            return branch_name
        # Branch doesn't exist or other non-fatal issue
        if "not found" in result.stderr.lower():
            return None
        logger.warning(
            "Failed to delete branch %s: %s",
            branch_name,
            result.stderr.strip(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Git branch delete failed for %s: %s", branch_name, exc)
    return None


def _cleanup_task(
    task_id: str,
    worktrees_dir: Path,
    repo_path: Path,
) -> tuple[str | None, str | None]:
    """Clean up worktree and branch for a single task.

    Args:
        task_id: The task identifier.
        worktrees_dir: Path to .agent-fox/worktrees/.
        repo_path: Path to the git repository root.

    Returns:
        Tuple of (cleaned_worktree, cleaned_branch) where each is
        the path/name if cleaned, or None.
    """
    wt = _clean_worktree(worktrees_dir, task_id)
    br = _clean_branch(repo_path, task_id)
    return wt, br


def _collect_cleanup(
    task_id: str,
    worktrees_dir: Path,
    repo_path: Path,
    cleaned_worktrees: list[str],
    cleaned_branches: list[str],
) -> None:
    """Clean up artifacts for a task and append results to the lists."""
    wt, br = _cleanup_task(task_id, worktrees_dir, repo_path)
    if wt:
        cleaned_worktrees.append(wt)
    if br:
        cleaned_branches.append(br)


def _find_sole_blocker_dependents(
    task_id: str,
    plan: TaskGraph,
    state: ExecutionState,
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
    unblockable: list[str] = []
    node_states = state.node_states

    for nid in plan.nodes:
        # Only consider blocked tasks
        if node_states.get(nid, "pending") != "blocked":
            continue

        # Check all predecessors
        preds = plan.predecessors(nid)
        if not preds:
            continue

        # The reset target must be one of the predecessors
        if task_id not in preds:
            continue

        # All non-reset predecessors must be completed
        all_others_completed = all(
            node_states.get(p, "pending") == "completed" for p in preds if p != task_id
        )

        if all_others_completed:
            unblockable.append(nid)

    return unblockable


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
    state = _load_state_or_raise(state_path)
    _load_plan_or_raise(plan_path)

    # Find all resettable tasks
    reset_tasks: list[str] = []
    cleaned_worktrees: list[str] = []
    cleaned_branches: list[str] = []

    for task_id, status in state.node_states.items():
        if status in _RESETTABLE_STATUSES:
            reset_tasks.append(task_id)

            _collect_cleanup(
                task_id,
                worktrees_dir,
                repo_path,
                cleaned_worktrees,
                cleaned_branches,
            )

    # Update state: set all reset tasks to pending
    if reset_tasks:
        for task_id in reset_tasks:
            state.node_states[task_id] = "pending"
        StateManager(state_path).save(state)

    return ResetResult(
        reset_tasks=reset_tasks,
        unblocked_tasks=[],  # Full reset has no cascade concept
        cleaned_worktrees=cleaned_worktrees,
        cleaned_branches=cleaned_branches,
    )


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
    state = _load_state_or_raise(state_path)
    plan = _load_plan_or_raise(plan_path)

    # Validate task ID exists in the plan
    if task_id not in plan.nodes:
        valid_ids = sorted(plan.nodes.keys())
        raise AgentFoxError(
            f"Unknown task ID: {task_id}. Valid task IDs: {', '.join(valid_ids)}",
            task_id=task_id,
        )

    # Check if the task is completed (cannot reset)
    current_status = state.node_states.get(task_id, "pending")
    if current_status == "completed":
        logger.warning(
            "Task %s is already completed and cannot be reset.",
            task_id,
        )
        return ResetResult(
            reset_tasks=[],
            unblocked_tasks=[],
            cleaned_worktrees=[],
            cleaned_branches=[],
            skipped_completed=[task_id],
        )

    # Reset the task
    reset_tasks: list[str] = [task_id]
    cleaned_worktrees: list[str] = []
    cleaned_branches: list[str] = []

    _collect_cleanup(
        task_id,
        worktrees_dir,
        repo_path,
        cleaned_worktrees,
        cleaned_branches,
    )

    # Update state for the target task
    state.node_states[task_id] = "pending"

    # Find and unblock downstream tasks where this was the sole blocker
    unblocked_tasks = _find_sole_blocker_dependents(task_id, plan, state)

    # Reset unblocked tasks to pending and clean up their artifacts
    for unblocked_id in unblocked_tasks:
        state.node_states[unblocked_id] = "pending"
        _collect_cleanup(
            unblocked_id,
            worktrees_dir,
            repo_path,
            cleaned_worktrees,
            cleaned_branches,
        )

    # Persist updated state
    StateManager(state_path).save(state)

    return ResetResult(
        reset_tasks=reset_tasks,
        unblocked_tasks=unblocked_tasks,
        cleaned_worktrees=cleaned_worktrees,
        cleaned_branches=cleaned_branches,
    )
