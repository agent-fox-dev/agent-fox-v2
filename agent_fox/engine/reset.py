"""Reset engine: clear failed/blocked tasks, cascade unblock, hard reset.

Requirements: 07-REQ-4.1, 07-REQ-4.2, 07-REQ-5.1, 07-REQ-5.2,
              35-REQ-3.1 .. 35-REQ-4.5, 35-REQ-7.1 .. 35-REQ-7.2
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from agent_fox.core.errors import AgentFoxError
from agent_fox.engine.reset_artifacts import (
    _cleanup_task,  # noqa: F401
    _task_id_to_branch_name,  # noqa: F401
    _task_id_to_worktree_path,  # noqa: F401
    collect_cleanup,
    find_affected_tasks,
    find_rollback_target,
    reset_plan_statuses,
    reset_tasks_md_checkboxes,
    rollback_develop,
)
from agent_fox.engine.state import ExecutionState, StateManager
from agent_fox.graph.persistence import load_plan_or_raise
from agent_fox.graph.types import TaskGraph
from agent_fox.knowledge.compaction import compact

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


def _load_state_or_raise(state_path: Path) -> ExecutionState:
    """Load execution state from state.jsonl, raising if missing."""
    return _load_or_raise(
        state_path,
        lambda p: StateManager(p).load(),
        "No execution state found. Run `agent-fox code` first.",
    )


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

    # Persist updated state
    StateManager(state_path).save(state)

    return ResetResult(
        reset_tasks=reset_tasks,
        unblocked_tasks=unblocked_tasks,
        cleaned_worktrees=cleaned_worktrees,
        cleaned_branches=cleaned_branches,
    )


def reset_spec(
    spec_name: str,
    state_path: Path,
    plan_path: Path,
    worktrees_dir: Path,
    repo_path: Path,
) -> ResetResult:
    """Reset all tasks belonging to a single spec to pending.

    Identifies all nodes (coder + archetype) whose spec_name matches,
    resets their state to pending, cleans worktrees/branches, and
    synchronizes tasks.md and plan.json.

    Does NOT perform git rollback or knowledge compaction.

    Args:
        spec_name: The spec folder name to reset.
        state_path: Path to .agent-fox/state.jsonl.
        plan_path: Path to .agent-fox/plan.json.
        worktrees_dir: Path to worktrees directory.
        repo_path: Path to the git repository root.

    Returns:
        ResetResult with reset_tasks, cleaned_worktrees, cleaned_branches.

    Raises:
        AgentFoxError: If spec_name not found in plan, or state/plan missing.

    Requirements: 50-REQ-1.1 .. 50-REQ-1.8, 50-REQ-4.1, 50-REQ-4.2
    """
    state = _load_state_or_raise(state_path)
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

    # Synchronize plan.json statuses (50-REQ-1.6)
    reset_plan_statuses(plan_path, spec_node_ids)

    # Save state — preserves session_history and counters (50-REQ-4.1, 50-REQ-4.2)
    if non_pending:
        StateManager(state_path).save(state)

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
    state_path: Path,
    plan_path: Path,
    worktrees_dir: Path,
    repo_path: Path,
    memory_path: Path,
    db_conn: duckdb.DuckDBPyConnection | None = None,
) -> HardResetResult:
    """Shared hard-reset logic: reset states, clean artifacts, compact, save.

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
    reset_plan_statuses(plan_path, affected_ids)

    # Save state (preserving counters and session history)
    StateManager(state_path).save(state)

    return HardResetResult(
        reset_tasks=affected_ids,
        cleaned_worktrees=cleaned_worktrees,
        cleaned_branches=cleaned_branches,
        compaction=compaction_result,
        rollback_sha=rollback_sha,
    )


def hard_reset_all(
    state_path: Path,
    plan_path: Path,
    worktrees_dir: Path,
    repo_path: Path,
    memory_path: Path,
    db_conn: duckdb.DuckDBPyConnection | None = None,
) -> HardResetResult:
    """Full hard reset: all tasks, all artifacts, code rollback.

    Requirements: 35-REQ-3.1 .. 35-REQ-3.7, 35-REQ-3.E1, 35-REQ-3.E2
    """
    state = _load_state_or_raise(state_path)
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
        state_path,
        plan_path,
        worktrees_dir,
        repo_path,
        memory_path,
        db_conn,
    )


def hard_reset_task(
    task_id: str,
    state_path: Path,
    plan_path: Path,
    worktrees_dir: Path,
    repo_path: Path,
    memory_path: Path,
    db_conn: duckdb.DuckDBPyConnection | None = None,
) -> HardResetResult:
    """Partial hard reset: target task + cascaded tasks, code rollback.

    Requirements: 35-REQ-4.1 .. 35-REQ-4.5, 35-REQ-4.E1, 35-REQ-4.E2
    """
    state = _load_state_or_raise(state_path)
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
        state_path,
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
    state_path: Path | None = None,
    plan_path: Path | None = None,
    worktrees_dir: Path | None = None,
    repo_path: Path | None = None,
    memory_path: Path | None = None,
    specs_dir: Path | None = None,
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
        state_path: Path to state.jsonl.
        plan_path: Path to plan.json.
        worktrees_dir: Path to worktrees directory.
        repo_path: Project root directory.
        memory_path: Path to memory.jsonl (needed for hard reset).
        specs_dir: Not used directly, reserved for future use.

    Returns:
        ResetResult or HardResetResult.

    Requirements: 59-REQ-5.1, 59-REQ-5.2, 59-REQ-5.3
    """
    from agent_fox.core.paths import AGENT_FOX_DIR

    project_root = repo_path or Path.cwd()
    agent_dir = project_root / AGENT_FOX_DIR
    resolved_state = state_path or agent_dir / "state.jsonl"
    resolved_plan = plan_path or agent_dir / "plan.json"
    resolved_worktrees = worktrees_dir or agent_dir / "worktrees"
    resolved_memory = memory_path or agent_dir / "memory.jsonl"

    if spec is not None:
        return reset_spec(
            spec_name=spec,
            state_path=resolved_state,
            plan_path=resolved_plan,
            worktrees_dir=resolved_worktrees,
            repo_path=project_root,
        )

    if hard:
        if target is not None:
            return hard_reset_task(
                task_id=target,
                state_path=resolved_state,
                plan_path=resolved_plan,
                worktrees_dir=resolved_worktrees,
                repo_path=project_root,
                memory_path=resolved_memory,
            )
        return hard_reset_all(
            state_path=resolved_state,
            plan_path=resolved_plan,
            worktrees_dir=resolved_worktrees,
            repo_path=project_root,
            memory_path=resolved_memory,
        )

    if target is not None:
        return reset_task(
            task_id=target,
            state_path=resolved_state,
            plan_path=resolved_plan,
            worktrees_dir=resolved_worktrees,
            repo_path=project_root,
        )

    return reset_all(
        state_path=resolved_state,
        plan_path=resolved_plan,
        worktrees_dir=resolved_worktrees,
        repo_path=project_root,
    )
