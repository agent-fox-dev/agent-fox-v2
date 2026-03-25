"""Barrier entry operations: worktree verification and bidirectional develop sync.

Encapsulates the operations that run at the start of a sync barrier,
before hooks and hot-loading. Keeps engine.py thin.

Requirements: 51-REQ-2.1, 51-REQ-2.2, 51-REQ-2.3, 51-REQ-2.E1,
              51-REQ-3.1, 51-REQ-3.2, 51-REQ-3.3, 51-REQ-3.E1,
              51-REQ-3.E2, 51-REQ-3.E3
"""

from __future__ import annotations

import logging
from pathlib import Path

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
