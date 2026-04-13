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

# Module-level import so tests can patch agent_fox.engine.barrier.run_consolidation.
# Falls back to None if the consolidation module is unavailable.
try:
    from agent_fox.knowledge.consolidation import run_consolidation
except ImportError:  # pragma: no cover
    run_consolidation = None  # type: ignore[assignment]


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


async def run_sync_barrier_sequence(
    *,
    state: Any,
    sync_interval: int,
    repo_root: Path,
    emit_audit: Callable[..., None],
    hook_config: Any | None,
    no_hooks: bool,
    specs_dir: Path | None,
    hot_load_enabled: bool,
    hot_load_fn: Callable[..., Any],
    sync_plan_fn: Callable[..., None],
    barrier_callback: Callable[[], None] | None,
    knowledge_db_conn: Any | None,
    reload_config_fn: Callable[[], None] | None = None,
    knowledge_config: Any | None = None,
    sink_dispatcher: Any | None = None,
    completed_specs_fn: Callable[[], set[str]] | None = None,
    consolidated_specs: set[str] | None = None,
) -> None:
    """Execute the sync barrier sequence.

    Called when the completed task count crosses a sync_interval boundary.

    Steps:
    1. Verify worktrees (51-REQ-2.*)
    2. Bidirectional develop sync (51-REQ-3.*)
    3. Run sync barrier hooks
    4. Hot-load new specs (with gated discovery)
    5. Barrier callback (knowledge ingestion)
    6. Regenerate memory summary

    Requirements: 06-REQ-6.1, 06-REQ-6.2, 06-REQ-6.3, 05-REQ-6.3,
                  51-REQ-2.*, 51-REQ-3.*
    """
    from agent_fox.hooks.hooks import run_sync_barrier_hooks
    from agent_fox.knowledge.audit import AuditEventType
    from agent_fox.knowledge.rendering import render_summary

    completed_count = _count_node_status(state.node_states, "completed")
    barrier_number = completed_count // sync_interval
    logger.info(
        "Sync barrier %d triggered at %d completed tasks",
        barrier_number,
        completed_count,
    )

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

    # 06-REQ-6.1: Run sync barrier hooks
    if hook_config is not None:
        run_sync_barrier_hooks(
            barrier_number=barrier_number,
            config=hook_config,
            no_hooks=no_hooks,
        )

    # 06-REQ-6.3: Hot-load new specs (with gated discovery)
    if specs_dir is not None and hot_load_enabled:
        try:
            await hot_load_fn(state)
            # Persist immediately so a crash doesn't lose new specs
            sync_plan_fn(state)
        except Exception:
            logger.warning("Hot-loading specs failed at barrier", exc_info=True)

    # 12-REQ-4.1, 12-REQ-4.2: Run barrier callback (knowledge ingestion)
    if barrier_callback is not None:
        try:
            barrier_callback()
        except Exception:
            logger.warning("Barrier callback failed", exc_info=True)

    # Compact knowledge base: deduplicate and resolve supersession (fixes #211)
    if knowledge_db_conn is not None:
        try:
            from agent_fox.knowledge.compaction import compact

            compact(knowledge_db_conn)
        except Exception:
            logger.warning("Knowledge compaction failed at barrier", exc_info=True)

    # 90-REQ-4.1, 90-REQ-4.2: Run fact lifecycle cleanup (decay + audit)
    if knowledge_db_conn is not None and knowledge_config is not None:
        try:
            from agent_fox.knowledge.lifecycle import run_cleanup

            cleanup_result = run_cleanup(
                knowledge_db_conn,
                knowledge_config,
                sink_dispatcher=sink_dispatcher,
            )
            logger.info(
                "Fact lifecycle cleanup: expired=%d deduped=%d contradicted=%d remaining=%d",
                cleanup_result.facts_expired,
                cleanup_result.facts_deduped,
                cleanup_result.facts_contradicted,
                cleanup_result.active_facts_remaining,
            )
        except Exception:
            logger.warning("Fact lifecycle cleanup failed at barrier", exc_info=True)

    # 96-REQ-7.1, 96-REQ-7.3: Run consolidation pipeline for newly completed specs.
    # Runs after lifecycle cleanup and before summary regeneration so that
    # the exclusive barrier window provides write isolation.
    if (
        run_consolidation is not None
        and knowledge_db_conn is not None
        and completed_specs_fn is not None
        and consolidated_specs is not None
    ):
        try:
            all_completed = completed_specs_fn()
            new_completed = all_completed - consolidated_specs
            if new_completed:
                consolidation_result = await run_consolidation(
                    knowledge_db_conn,
                    repo_root,
                    new_completed,
                    model="claude-3-5-haiku-20241022",
                    sink_dispatcher=sink_dispatcher,
                )
                consolidated_specs.update(new_completed)
                logger.info(
                    "Consolidation complete at barrier: linked=%d errors=%s",
                    consolidation_result.facts_linked,
                    consolidation_result.errors,
                )
        except Exception:
            logger.warning("Consolidation pipeline failed at barrier", exc_info=True)

    # 06-REQ-6.2 / 05-REQ-6.3: Regenerate memory summary
    try:
        render_summary(conn=knowledge_db_conn)
    except Exception:
        logger.warning("Memory summary regeneration failed", exc_info=True)

    # 66-REQ-1.1: Reload configuration after barrier completes
    if reload_config_fn is not None:
        try:
            reload_config_fn()
        except Exception:
            logger.warning("Config reload failed at barrier", exc_info=True)
