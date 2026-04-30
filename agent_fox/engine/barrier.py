"""Barrier operations: worktree verification, develop sync, and barrier sequence.

Encapsulates the operations that run at sync barriers: worktree
verification, bidirectional develop sync, hooks, hot-loading, and
knowledge ingestion. Keeps engine.py thin.

Requirements: 51-REQ-2.1, 51-REQ-2.2, 51-REQ-2.3, 51-REQ-2.E1,
              51-REQ-3.1, 51-REQ-3.2, 51-REQ-3.3, 51-REQ-3.E1,
              51-REQ-3.E2, 51-REQ-3.E3,
              06-REQ-6.1, 06-REQ-6.2, 06-REQ-6.3, 05-REQ-6.3,
              96-REQ-7.1, 96-REQ-7.3
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_fox.workspace.develop import _sync_develop_with_remote
from agent_fox.workspace.git import run_git
from agent_fox.workspace.merge_lock import MergeLock

logger = logging.getLogger(__name__)


def verify_worktrees(repo_root: Path) -> list[Path]:
    """Scan .agent-fox/worktrees/ for orphaned directories.

    Returns list of orphaned paths (empty if none found).
    Logs a warning per orphaned path.

    Requirements: 51-REQ-2.1, 51-REQ-2.2, 51-REQ-2.3, 51-REQ-2.E1
    """
    worktrees_dir = repo_root / ".agent-fox" / "worktrees"

    # 51-REQ-2.E1: missing directory is treated as no orphans
    if not worktrees_dir.exists():
        return []

    orphans: list[Path] = []
    for child in worktrees_dir.iterdir():
        if child.is_dir():
            orphans.append(child)

    # 51-REQ-2.2: log warning for each orphaned path
    for orphan in orphans:
        logger.warning("Orphaned worktree directory found: %s", orphan)

    return orphans


async def sync_develop_bidirectional(repo_root: Path) -> None:
    """Pull remote into local develop, then push local to origin.

    Acquires MergeLock for the entire operation.
    Logs warnings on failure but does not raise.

    Requirements: 51-REQ-3.1, 51-REQ-3.2, 51-REQ-3.3, 51-REQ-3.E1,
                  51-REQ-3.E2, 51-REQ-3.E3
    """
    # 51-REQ-3.E3: check if origin remote exists
    try:
        await run_git(["remote", "get-url", "origin"], cwd=repo_root)
    except Exception:
        logger.debug("No origin remote found; skipping develop sync")
        return

    # 51-REQ-3.3: acquire MergeLock for entire operation
    lock = MergeLock(repo_root)
    async with lock:
        # 51-REQ-3.1: pull sync
        try:
            await _sync_develop_with_remote(repo_root)
        except Exception:
            # 51-REQ-3.E1: pull failure — log warning, skip push
            logger.warning(
                "Develop pull sync failed; skipping push to origin",
                exc_info=True,
            )
            return

        # 51-REQ-3.2: push local develop to origin
        try:
            await run_git(
                ["push", "origin", "develop"],
                cwd=repo_root,
                check=True,
            )
        except Exception:
            # 51-REQ-3.E2: push failure — non-blocking
            logger.warning(
                "Failed to push develop to origin; proceeding",
                exc_info=True,
            )


def _count_node_status(node_states: dict[str, str], status: str) -> int:
    """Count nodes with a given status."""
    return sum(1 for s in node_states.values() if s == status)


# Ordered list of statuses shown in the progress line (issue #588).
_PROGRESS_STATUSES = ("completed", "in_progress", "pending", "blocked", "failed")


def _format_progress_line(node_states: dict[str, str]) -> str:
    """Return a single-line progress summary, e.g. 'completed: 4 | pending: 2'.

    Only statuses with a non-zero count are included.
    """
    parts = [
        f"{status}: {count}" for status in _PROGRESS_STATUSES if (count := _count_node_status(node_states, status))
    ]
    return " | ".join(parts) if parts else "no tasks"


async def run_sync_barrier_sequence(
    *,
    state: Any,
    sync_interval: int,
    repo_root: Path,
    emit_audit: Callable[..., None],
    specs_dir: Path | None,
    hot_load_enabled: bool,
    hot_load_fn: Callable[..., Any],
    sync_plan_fn: Callable[..., None],
    barrier_callback: Callable[[], None] | None,
    knowledge_db_conn: Any | None = None,
    reload_config_fn: Callable[[], None] | None = None,
) -> None:
    """Execute the sync barrier sequence.

    Called when the completed task count crosses a sync_interval boundary.

    Retained operational steps:
    1. Verify worktrees (51-REQ-2.*)
    2. Bidirectional develop sync (51-REQ-3.*)
    3. Hot-load new specs (with gated discovery)
    4. Barrier callback
    5. Config reload

    Knowledge-related steps (fact consolidation, deduplication, lifecycle
    cleanup, sleep pre-computation, summary rendering) were removed by
    spec 114 (knowledge decoupling).

    Requirements: 06-REQ-6.1, 06-REQ-6.2, 06-REQ-6.3,
                  51-REQ-2.*, 51-REQ-3.*, 114-REQ-5.1, 114-REQ-5.2
    """
    from agent_fox.knowledge.audit import AuditEventType

    completed_count = _count_node_status(state.node_states, "completed")
    barrier_number = completed_count // sync_interval
    logger.info(
        "Sync barrier %d triggered at %d completed tasks",
        barrier_number,
        completed_count,
    )

    # Print a brief one-line progress summary (issue #588).
    # Guarded so a broken pipe or other I/O error never aborts the sequence.
    try:
        print(f"[barrier] {_format_progress_line(state.node_states)}", flush=True)
    except Exception:
        logger.debug("Failed to print barrier progress line", exc_info=True)

    # 51-REQ-2.1: Verify worktrees for orphans
    orphaned_worktrees: list[str] = []
    try:
        orphans = verify_worktrees(repo_root)
        orphaned_worktrees = [str(p) for p in orphans]
    except Exception:
        logger.warning("Worktree verification failed", exc_info=True)

    # 51-REQ-3.1, 51-REQ-3.2: Bidirectional develop sync
    develop_sync_status = "success"
    try:
        await sync_develop_bidirectional(repo_root)
    except Exception:
        develop_sync_status = "failed"
        logger.warning("Bidirectional develop sync failed", exc_info=True)

    # 40-REQ-9.5: Emit sync.barrier audit event (extended payload)
    completed_nodes = [nid for nid, s in state.node_states.items() if s == "completed"]
    pending_nodes = [nid for nid, s in state.node_states.items() if s in ("pending", "in_progress")]
    emit_audit(
        AuditEventType.SYNC_BARRIER,
        payload={
            "completed_nodes": completed_nodes,
            "pending_nodes": pending_nodes,
            "orphaned_worktrees": orphaned_worktrees,
            "develop_sync_status": develop_sync_status,
            "specs_skipped": {},
        },
    )

    # 06-REQ-6.3: Hot-load new specs (with gated discovery)
    if specs_dir is not None and hot_load_enabled:
        try:
            await hot_load_fn(state)
            # Persist immediately so a crash doesn't lose new specs
            sync_plan_fn(state)
        except Exception:
            logger.warning("Hot-loading specs failed at barrier", exc_info=True)

    # 12-REQ-4.1, 12-REQ-4.2: Run barrier callback
    if barrier_callback is not None:
        try:
            barrier_callback()
        except Exception:
            logger.warning("Barrier callback failed", exc_info=True)

    # 66-REQ-1.1: Reload configuration after barrier completes
    if reload_config_fn is not None:
        try:
            reload_config_fn()
        except Exception:
            logger.warning("Config reload failed at barrier", exc_info=True)
