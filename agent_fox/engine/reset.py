"""Reset engine: clear failed/blocked tasks, cascade unblock, hard reset.

Requirements: 07-REQ-4.1, 07-REQ-4.2, 07-REQ-5.1, 07-REQ-5.2,
              35-REQ-3.1 .. 35-REQ-4.5, 35-REQ-7.1 .. 35-REQ-7.2
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

from agent_fox.core.errors import AgentFoxError
from agent_fox.core.node_id import parse_node_id
from agent_fox.engine.state import (
    ExecutionState,
    SessionRecord,
    load_state_from_db,
    persist_node_status,
)
from agent_fox.graph.persistence import load_plan_or_raise
from agent_fox.graph.types import TaskGraph
from agent_fox.knowledge.compaction import compact

logger = logging.getLogger(__name__)

# Statuses that qualify for reset (not completed, pending, or skipped)
_RESETTABLE_STATUSES = frozenset({"failed", "blocked", "in_progress"})


def _persist_resets(
    db_conn: duckdb.DuckDBPyConnection | None,
    task_ids: list[str],
) -> None:
    """Persist reset node statuses to DB."""
    if db_conn is None:
        return
    try:
        for task_id in task_ids:
            persist_node_status(db_conn, task_id, "pending", blocked_reason=None)
    except Exception:
        logger.debug("Failed to persist resets to DB", exc_info=True)


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


@dataclass(frozen=True)
class HardResetResult:
    """Result of a hard reset operation."""

    reset_tasks: list[str]  # all task IDs reset to pending
    cleaned_worktrees: list[str]  # worktree dirs removed
    cleaned_branches: list[str]  # local branches deleted
    compaction: tuple[int, int]  # (original_count, surviving_count)
    rollback_sha: str | None  # target commit SHA, or None if skipped


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


def _load_state_or_raise(
    db_conn: duckdb.DuckDBPyConnection | None,
) -> ExecutionState:
    """Load execution state from DB, raising if missing.

    Requirements: 105-REQ-5.3 (no StateManager/JSONL)
    """
    if db_conn is None:
        raise AgentFoxError(
            "No database connection available. Run `agent-fox code` first.",
        )
    state = load_state_from_db(db_conn)
    if state is None:
        raise AgentFoxError(
            "No execution state found. Run `agent-fox code` first.",
        )
    return state


def _load_plan_or_raise(plan_path: Path) -> TaskGraph:
    """Load the task graph from plan.json, raising on failure."""
    return load_plan_or_raise(plan_path)


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
        all_others_completed = all(node_states.get(p, "pending") == "completed" for p in preds if p != task_id)

        if all_others_completed:
            unblockable.append(nid)

    return unblockable


def reset_all(
    plan_path: Path,
    worktrees_dir: Path,
    repo_path: Path,
    db_conn: duckdb.DuckDBPyConnection | None = None,
) -> ResetResult:
    """Reset all incomplete tasks to pending.

    Resets tasks with status failed, blocked, or in_progress.
    Cleans up worktree directories and feature branches.

    Args:
        plan_path: Path to .agent-fox/plan.json.
        worktrees_dir: Path to .agent-fox/worktrees/.
        repo_path: Path to the git repository root.
        db_conn: DuckDB connection for state persistence.

    Returns:
        ResetResult summarizing what was reset.

    Raises:
        AgentFoxError: If state or plan files are missing.
    """
    state = _load_state_or_raise(db_conn)
    _load_plan_or_raise(plan_path)

    # Find all resettable tasks
    reset_tasks: list[str] = []
    cleaned_worktrees: list[str] = []
    cleaned_branches: list[str] = []

    for task_id, status in state.node_states.items():
        if status in _RESETTABLE_STATUSES:
            reset_tasks.append(task_id)

            collect_cleanup(
                task_id,
                worktrees_dir,
                repo_path,
                cleaned_worktrees,
                cleaned_branches,
            )

    # Update state: set all reset tasks to pending and clear stale reasons
    if reset_tasks:
        for task_id in reset_tasks:
            state.node_states[task_id] = "pending"
            state.blocked_reasons.pop(task_id, None)
        _persist_resets(db_conn, reset_tasks)

    return ResetResult(
        reset_tasks=reset_tasks,
        unblocked_tasks=[],  # Full reset has no cascade concept
        cleaned_worktrees=cleaned_worktrees,
        cleaned_branches=cleaned_branches,
    )


def reset_task(
    task_id: str,
    plan_path: Path,
    worktrees_dir: Path,
    repo_path: Path,
    db_conn: duckdb.DuckDBPyConnection | None = None,
) -> ResetResult:
    """Reset a single task and re-evaluate downstream blockers.

    If the reset task was the sole blocker for a downstream task,
    that downstream task is also reset to pending.

    Args:
        task_id: The task identifier to reset.
        plan_path: Path to .agent-fox/plan.json.
        worktrees_dir: Path to .agent-fox/worktrees/.
        repo_path: Path to the git repository root.
        db_conn: DuckDB connection for state persistence.

    Returns:
        ResetResult summarizing what was reset and unblocked.

    Raises:
        AgentFoxError: If the task ID is not found in the plan.
        AgentFoxError: If the task is already completed.
    """
    state = _load_state_or_raise(db_conn)
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

    collect_cleanup(
        task_id,
        worktrees_dir,
        repo_path,
        cleaned_worktrees,
        cleaned_branches,
    )

    # Update state for the target task
    state.node_states[task_id] = "pending"
    state.blocked_reasons.pop(task_id, None)

    # Find and unblock downstream tasks where this was the sole blocker
    unblocked_tasks = _find_sole_blocker_dependents(task_id, plan, state)

    # Reset unblocked tasks to pending and clean up their artifacts
    for unblocked_id in unblocked_tasks:
        state.node_states[unblocked_id] = "pending"
        state.blocked_reasons.pop(unblocked_id, None)
        collect_cleanup(
            unblocked_id,
            worktrees_dir,
            repo_path,
            cleaned_worktrees,
            cleaned_branches,
        )

    # Persist updated state to DB
    _persist_resets(db_conn, reset_tasks + unblocked_tasks)

    return ResetResult(
        reset_tasks=reset_tasks,
        unblocked_tasks=unblocked_tasks,
        cleaned_worktrees=cleaned_worktrees,
        cleaned_branches=cleaned_branches,
    )


def reset_spec(
    spec_name: str,
    plan_path: Path,
    worktrees_dir: Path,
    repo_path: Path,
    db_conn: duckdb.DuckDBPyConnection | None = None,
) -> ResetResult:
    """Reset all tasks belonging to a single spec to pending.

    Identifies all nodes (coder + archetype) whose spec_name matches,
    resets their state to pending, cleans worktrees/branches, and
    synchronizes tasks.md and DB statuses.

    Does NOT perform git rollback or knowledge compaction.

    Args:
        spec_name: The spec folder name to reset.
        plan_path: Path to .agent-fox/plan.json.
        worktrees_dir: Path to worktrees directory.
        repo_path: Path to the git repository root.
        db_conn: DuckDB connection for state persistence.

    Returns:
        ResetResult with reset_tasks, cleaned_worktrees, cleaned_branches.

    Raises:
        AgentFoxError: If spec_name not found in plan, or state/plan missing.

    Requirements: 50-REQ-1.1 .. 50-REQ-1.8, 50-REQ-4.1, 50-REQ-4.2
    """
    state = _load_state_or_raise(db_conn)
    plan = _load_plan_or_raise(plan_path)

    # Collect all node IDs belonging to the target spec
    spec_node_ids = [nid for nid, node in plan.nodes.items() if node.spec_name == spec_name]

    # Validate spec exists in plan (50-REQ-1.E1)
    if not spec_node_ids:
        valid_specs = sorted({node.spec_name for node in plan.nodes.values()})
        raise AgentFoxError(
            f"Unknown spec: {spec_name}. Valid specs: {', '.join(valid_specs)}",
            spec_name=spec_name,
        )

    # Identify nodes that are not already pending (50-REQ-1.E4)
    non_pending = [nid for nid in spec_node_ids if state.node_states.get(nid, "pending") != "pending"]

    # Reset matching node_states to pending (50-REQ-1.1, 50-REQ-1.2)
    for nid in spec_node_ids:
        state.node_states[nid] = "pending"
        state.blocked_reasons.pop(nid, None)

    # Clean worktrees and branches (50-REQ-1.4)
    cleaned_worktrees: list[str] = []
    cleaned_branches: list[str] = []
    for nid in spec_node_ids:
        collect_cleanup(nid, worktrees_dir, repo_path, cleaned_worktrees, cleaned_branches)

    # Synchronize tasks.md checkboxes (50-REQ-1.5)
    specs_dir = repo_path / ".specs"
    reset_tasks_md_checkboxes(spec_node_ids, specs_dir)

    # Persist to DB (50-REQ-4.1, 50-REQ-4.2)
    if non_pending:
        _persist_resets(db_conn, spec_node_ids)

    return ResetResult(
        reset_tasks=non_pending,
        unblocked_tasks=[],
        cleaned_worktrees=cleaned_worktrees,
        cleaned_branches=cleaned_branches,
    )


def _perform_hard_reset(
    state: ExecutionState,
    affected_ids: list[str],
    rollback_sha: str | None,
    plan_path: Path,
    worktrees_dir: Path,
    repo_path: Path,
    memory_path: Path,
    db_conn: duckdb.DuckDBPyConnection | None = None,
) -> HardResetResult:
    """Shared hard-reset logic: reset states, clean artifacts, compact, persist.

    Used by both hard_reset_all and hard_reset_task.
    """
    # Reset affected tasks to pending
    for tid in affected_ids:
        state.node_states[tid] = "pending"
        state.blocked_reasons.pop(tid, None)

    # Clean worktrees and branches
    cleaned_worktrees: list[str] = []
    cleaned_branches: list[str] = []
    for tid in affected_ids:
        collect_cleanup(tid, worktrees_dir, repo_path, cleaned_worktrees, cleaned_branches)

    # Compact knowledge base
    compaction_result = compact(db_conn, memory_path) if db_conn is not None else (0, 0)

    # Reset artifact synchronization
    specs_dir = repo_path / ".specs"
    reset_tasks_md_checkboxes(affected_ids, specs_dir)

    # Persist resets to DB
    _persist_resets(db_conn, affected_ids)

    return HardResetResult(
        reset_tasks=affected_ids,
        cleaned_worktrees=cleaned_worktrees,
        cleaned_branches=cleaned_branches,
        compaction=compaction_result,
        rollback_sha=rollback_sha,
    )


def hard_reset_all(
    plan_path: Path,
    worktrees_dir: Path,
    repo_path: Path,
    memory_path: Path,
    db_conn: duckdb.DuckDBPyConnection | None = None,
) -> HardResetResult:
    """Full hard reset: all tasks, all artifacts, code rollback.

    Requirements: 35-REQ-3.1 .. 35-REQ-3.7, 35-REQ-3.E1, 35-REQ-3.E2
    """
    state = _load_state_or_raise(db_conn)
    _load_plan_or_raise(plan_path)

    # Determine rollback target
    rollback_sha: str | None = None
    target = find_rollback_target(state.session_history, repo_path)
    if target is not None:
        try:
            rollback_develop(repo_path, target)
            rollback_sha = target
        except AgentFoxError:
            logger.warning("Rollback failed, skipping code rollback.")

    return _perform_hard_reset(
        state,
        list(state.node_states.keys()),
        rollback_sha,
        plan_path,
        worktrees_dir,
        repo_path,
        memory_path,
        db_conn,
    )


def hard_reset_task(
    task_id: str,
    plan_path: Path,
    worktrees_dir: Path,
    repo_path: Path,
    memory_path: Path,
    db_conn: duckdb.DuckDBPyConnection | None = None,
) -> HardResetResult:
    """Partial hard reset: target task + cascaded tasks, code rollback.

    Requirements: 35-REQ-4.1 .. 35-REQ-4.5, 35-REQ-4.E1, 35-REQ-4.E2
    """
    state = _load_state_or_raise(db_conn)
    plan = _load_plan_or_raise(plan_path)

    # Validate task_id
    if task_id not in plan.nodes:
        valid_ids = sorted(plan.nodes.keys())
        raise AgentFoxError(
            f"Unknown task ID: {task_id}. Valid task IDs: {', '.join(valid_ids)}",
            task_id=task_id,
        )

    # Find commit_sha for target task from session history
    target_sha: str | None = None
    for record in state.session_history:
        if record.node_id == task_id and record.commit_sha and record.status == "completed":
            target_sha = record.commit_sha
            break

    # Determine rollback target and find affected tasks
    rollback_sha: str | None = None
    affected_ids: list[str] = [task_id]

    if target_sha:
        target = find_rollback_target(state.session_history, repo_path, target_commit_sha=target_sha)
        if target is not None:
            try:
                rollback_develop(repo_path, target)
            except AgentFoxError:
                logger.warning("Rollback failed, skipping code rollback.")
            else:
                rollback_sha = target
                cascaded = find_affected_tasks(state.session_history, target, repo_path)
                affected_ids.extend(tid for tid in cascaded if tid not in affected_ids)

    return _perform_hard_reset(
        state,
        affected_ids,
        rollback_sha,
        plan_path,
        worktrees_dir,
        repo_path,
        memory_path,
        db_conn,
    )


def run_reset(
    target: str | None = None,
    config: object | None = None,
    *,
    soft: bool = True,
    hard: bool = False,
    spec: str | None = None,
    plan_path: Path | None = None,
    worktrees_dir: Path | None = None,
    repo_path: Path | None = None,
    memory_path: Path | None = None,
    specs_dir: Path | None = None,
    db_conn: duckdb.DuckDBPyConnection | None = None,
) -> ResetResult | HardResetResult:
    """Reset task state.

    Convenience wrapper that selects the appropriate reset function
    based on the provided arguments. Can be called without the CLI.

    Args:
        target: Optional task ID to reset. If None, resets all.
        config: Optional AgentFoxConfig (used to derive paths if not given).
        soft: Perform a soft reset (default).
        hard: Perform a hard reset (overrides soft).
        spec: Reset all tasks for a single spec.
        plan_path: Path to plan.json.
        worktrees_dir: Path to worktrees directory.
        repo_path: Project root directory.
        memory_path: Path to memory.jsonl (needed for hard reset).
        specs_dir: Not used directly, reserved for future use.
        db_conn: DuckDB connection for state persistence.

    Returns:
        ResetResult or HardResetResult.

    Requirements: 59-REQ-5.1, 59-REQ-5.2, 59-REQ-5.3
    """
    from agent_fox.core.paths import AGENT_FOX_DIR

    project_root = repo_path or Path.cwd()
    agent_dir = project_root / AGENT_FOX_DIR
    resolved_plan = plan_path or agent_dir / "plan.json"
    resolved_worktrees = worktrees_dir or agent_dir / "worktrees"
    resolved_memory = memory_path or agent_dir / "memory.jsonl"

    if spec is not None:
        return reset_spec(
            spec_name=spec,
            plan_path=resolved_plan,
            worktrees_dir=resolved_worktrees,
            repo_path=project_root,
            db_conn=db_conn,
        )

    if hard:
        if target is not None:
            return hard_reset_task(
                task_id=target,
                plan_path=resolved_plan,
                worktrees_dir=resolved_worktrees,
                repo_path=project_root,
                memory_path=resolved_memory,
                db_conn=db_conn,
            )
        return hard_reset_all(
            plan_path=resolved_plan,
            worktrees_dir=resolved_worktrees,
            repo_path=project_root,
            memory_path=resolved_memory,
            db_conn=db_conn,
        )

    if target is not None:
        return reset_task(
            task_id=target,
            plan_path=resolved_plan,
            worktrees_dir=resolved_worktrees,
            repo_path=project_root,
            db_conn=db_conn,
        )

    return reset_all(
        plan_path=resolved_plan,
        worktrees_dir=resolved_worktrees,
        repo_path=project_root,
        db_conn=db_conn,
    )


# ---------------------------------------------------------------------------
# Artifact helpers (inlined from reset_artifacts.py)
#
# Requirements: 07-REQ-4.1, 07-REQ-4.2, 35-REQ-3.1 .. 35-REQ-4.5
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Worktree / branch cleanup
# ---------------------------------------------------------------------------


def _task_id_to_worktree_path(worktrees_dir: Path, task_id: str) -> Path:
    """Convert a task ID to its worktree directory path.

    Task ID format: "spec_name:group_number"
    Worktree path: worktrees_dir / spec_name / group_number
    """
    parsed = parse_node_id(task_id)
    if parsed.group_number:
        return worktrees_dir / parsed.spec_name / str(parsed.group_number)
    return worktrees_dir / task_id


def _task_id_to_branch_name(task_id: str) -> str:
    """Convert a task ID to its feature branch name.

    Task ID format: "spec_name:group_number"
    Branch name: "feature/spec_name/group_number"

    Must match the format used by ``workspace.py:create_worktree``.
    """
    parsed = parse_node_id(task_id)
    if parsed.group_number:
        return f"feature/{parsed.spec_name}/{parsed.group_number}"
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


def _prune_worktrees(repo_path: Path) -> None:
    """Run ``git worktree prune`` to remove stale worktree tracking entries.

    After a worktree directory is deleted with shutil.rmtree, git's internal
    tracking (under ``.git/worktrees/``) still references it.  Without pruning,
    ``git branch -D`` will refuse to delete the associated branch because git
    believes the worktree is still active.
    """
    try:
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("git worktree prune failed: %s", exc)


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
    if wt:
        _prune_worktrees(repo_path)
    br = _clean_branch(repo_path, task_id)
    return wt, br


def collect_cleanup(
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


# ---------------------------------------------------------------------------
# Git rollback helpers
# ---------------------------------------------------------------------------


def find_rollback_target(
    session_history: list[SessionRecord],
    repo_path: Path,
    target_commit_sha: str | None = None,
) -> str | None:
    """Determine the rollback commit SHA.

    For full reset (target_commit_sha=None): finds the earliest
    commit_sha in session_history and returns its first-parent
    predecessor on develop.

    For partial reset (target_commit_sha given): returns the
    first-parent predecessor of target_commit_sha on develop.

    Returns None if no valid rollback target can be determined.
    """
    if target_commit_sha is not None:
        sha = target_commit_sha
    else:
        # Find earliest non-empty commit_sha in session history
        shas = [r.commit_sha for r in session_history if r.commit_sha and r.status == "completed"]
        if not shas:
            return None
        sha = shas[0]  # First in history order = earliest

    # Get the first-parent predecessor
    try:
        result = subprocess.run(
            ["git", "rev-parse", f"{sha}~1"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "Cannot resolve rollback target for %s: %s",
                sha,
                result.stderr.strip(),
            )
            return None
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Git rev-parse failed for %s: %s", sha, exc)
        return None


def rollback_develop(
    repo_path: Path,
    target_sha: str,
) -> None:
    """Reset the develop branch to the given commit SHA.

    Checks out develop and runs git reset --hard <target_sha>.

    Raises:
        AgentFoxError: If the SHA cannot be resolved.
    """
    try:
        # Checkout develop
        checkout_result = subprocess.run(
            ["git", "checkout", "develop"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if checkout_result.returncode != 0:
            raise AgentFoxError(f"Failed to checkout develop: {checkout_result.stderr.strip()}")

        # Reset to target SHA
        reset_result = subprocess.run(
            ["git", "reset", "--hard", target_sha],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if reset_result.returncode != 0:
            raise AgentFoxError(f"Failed to reset develop to {target_sha}: {reset_result.stderr.strip()}")
        logger.info("Rolled back develop to %s", target_sha)
    except (OSError, subprocess.SubprocessError) as exc:
        raise AgentFoxError(f"Git rollback failed: {exc}") from exc


def find_affected_tasks(
    session_history: list[SessionRecord],
    new_head: str,
    repo_path: Path,
) -> list[str]:
    """Find task IDs whose commit_sha is not an ancestor of new_head.

    Uses ``git merge-base --is-ancestor`` to check each completed
    task's commit_sha against the new develop HEAD.
    """
    affected: list[str] = []
    for record in session_history:
        if not record.commit_sha or record.status != "completed":
            continue
        try:
            result = subprocess.run(
                [
                    "git",
                    "merge-base",
                    "--is-ancestor",
                    record.commit_sha,
                    new_head,
                ],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                # Not an ancestor => affected by rollback
                affected.append(record.node_id)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning(
                "merge-base check failed for %s: %s",
                record.node_id,
                exc,
            )
            affected.append(record.node_id)
    return affected


# ---------------------------------------------------------------------------
# Spec file synchronization (tasks.md checkboxes)
# ---------------------------------------------------------------------------

# Pattern matching a top-level task group line: "- [...] N."
_TOP_LEVEL_RE = re.compile(r"^- \[.\] \d+\.", re.MULTILINE)

# Pattern matching any checkbox with [x] or [-] (at any indent level)
_CHECKBOX_RE = re.compile(r"^(\s*- \[)[x\-](\] )", re.MULTILINE)


def reset_tasks_md_checkboxes(
    affected_task_ids: list[str],
    specs_dir: Path,
) -> None:
    """Reset tasks.md checkboxes for affected task groups to ``[ ]``.

    For each affected task ID (format: spec_name:group_number),
    finds the corresponding tasks.md, locates the top-level
    checkbox for that group number, and replaces ``[x]`` or ``[-]``
    with ``[ ]``. Skips missing files silently.
    """
    # Group task IDs by spec name
    spec_groups: dict[str, list[int]] = {}
    for task_id in affected_task_ids:
        parsed = parse_node_id(task_id)
        if not parsed.group_number:
            continue
        spec_groups.setdefault(parsed.spec_name, []).append(parsed.group_number)

    for spec_name, group_nums in spec_groups.items():
        tasks_md = specs_dir / spec_name / "tasks.md"
        if not tasks_md.exists():
            logger.info("Skipping missing tasks.md for spec %s", spec_name)
            continue

        text = tasks_md.read_text()
        for group_num in group_nums:
            text = _reset_group_checkboxes(text, group_num)

        tasks_md.write_text(text)


def _reset_group_checkboxes(text: str, group_num: int) -> str:
    """Reset all checkboxes within a task group section to ``[ ]``.

    Identifies the section belonging to *group_num* (from its top-level
    ``- [...] N.`` line to the next top-level line or EOF) and resets
    every ``[x]`` or ``[-]`` checkbox within that section.
    """
    # Find the top-level line for this group
    group_start_re = re.compile(rf"^- \[[x\- ]\] {group_num}\.", re.MULTILINE)
    match = group_start_re.search(text)
    if not match:
        return text

    section_start = match.start()

    # Find the next top-level group line after this one
    next_match = _TOP_LEVEL_RE.search(text, match.end())
    section_end = next_match.start() if next_match else len(text)

    # Extract the section, reset all [x]/[-] checkboxes, reassemble
    before = text[:section_start]
    section = text[section_start:section_end]
    after = text[section_end:]

    section = _CHECKBOX_RE.sub(r"\1 \2", section)

    return before + section + after
