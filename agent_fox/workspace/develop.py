"""Develop branch management: ensure, sync, and reconcile.

Requirements: 19-REQ-1.1 through 19-REQ-1.6,
              45-REQ-3.2, 45-REQ-5.1, 45-REQ-5.2, 45-REQ-5.E1, 45-REQ-6.2
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent_fox.core.errors import WorkspaceError
from agent_fox.workspace.git import (
    detect_default_branch,
    local_branch_exists,
    remote_branch_exists,
    run_git,
)
from agent_fox.workspace.merge_agent import run_merge_agent
from agent_fox.workspace.merge_lock import MergeLock

logger = logging.getLogger(__name__)


async def ensure_develop(repo_root: Path) -> None:
    """Ensure a local develop branch exists and is up-to-date.

    1. Fetch origin (warn and continue on failure).
    2. If local develop exists:
       a. If origin/develop exists and local is behind, fast-forward.
       b. If diverged, warn and use local as-is.
    3. If local develop does not exist:
       a. If origin/develop exists, create tracking branch.
       b. Otherwise, create from default branch.

    Raises:
        WorkspaceError: If no suitable base branch can be found.

    Requirements: 19-REQ-1.1, 19-REQ-1.2, 19-REQ-1.3, 19-REQ-1.5, 19-REQ-1.6
    """
    # Step 1: Fetch origin (best-effort)
    fetch_ok = True
    try:
        await run_git(["fetch", "origin"], cwd=repo_root)
    except WorkspaceError:
        logger.warning("Failed to fetch from origin; proceeding with local state only")
        fetch_ok = False

    has_local = await local_branch_exists(repo_root, "develop")

    if has_local:
        # Local develop exists — check if we need to fast-forward
        if fetch_ok:
            has_remote = await remote_branch_exists(repo_root, "develop")
            if has_remote:
                await _sync_develop_with_remote(repo_root)
        # 19-REQ-1.E1: local exists and is up-to-date → no-op
        logger.info("Local develop branch is ready")
        return

    # No local develop — need to create it
    if fetch_ok:
        has_remote = await remote_branch_exists(repo_root, "develop")
        if has_remote:
            # 19-REQ-1.2: Create from origin/develop
            await run_git(
                ["branch", "develop", "origin/develop"],
                cwd=repo_root,
            )
            logger.info("Created local develop branch tracking origin/develop")
            return

    # 19-REQ-1.3: No remote develop — create from default branch
    default_branch = await detect_default_branch(repo_root)
    await run_git(
        ["branch", "develop", default_branch],
        cwd=repo_root,
    )
    logger.info("Created local develop branch from '%s'", default_branch)


async def _sync_develop_with_remote(repo_root: Path) -> None:
    """Synchronize local develop with origin/develop.

    Checks commit counts to determine if local is behind, ahead,
    or diverged from remote. Fast-forwards if behind only.

    All operations are wrapped in the merge lock to serialize access
    to the develop branch (45-REQ-3.2).

    Requirements: 19-REQ-1.6, 19-REQ-1.E1, 19-REQ-1.E4,
                  45-REQ-3.2, 45-REQ-5.1, 45-REQ-5.2, 45-REQ-5.E1, 45-REQ-6.2
    """
    lock = MergeLock(repo_root)
    async with lock:
        await _sync_develop_under_lock(repo_root)


async def _sync_develop_under_lock(repo_root: Path) -> None:
    """Execute the develop sync strategies under the merge lock.

    Called from _sync_develop_with_remote() after the lock is acquired.
    """
    # Commits on remote not on local (remote is ahead)
    _rc, remote_ahead_str, _stderr = await run_git(
        ["rev-list", "--count", "develop..origin/develop"],
        cwd=repo_root,
        check=False,
    )
    remote_ahead = int(remote_ahead_str.strip()) if remote_ahead_str.strip() else 0

    # Commits on local not on remote (local is ahead)
    _rc, local_ahead_str, _stderr = await run_git(
        ["rev-list", "--count", "origin/develop..develop"],
        cwd=repo_root,
        check=False,
    )
    local_ahead = int(local_ahead_str.strip()) if local_ahead_str.strip() else 0

    if remote_ahead == 0:
        # Local is up-to-date or ahead — no-op (19-REQ-1.E1)
        return

    if local_ahead > 0 and remote_ahead > 0:
        # Diverged — attempt rebase to reconcile
        logger.info(
            "Local develop has diverged from origin/develop "
            "(%d local, %d remote commits). Attempting rebase.",
            local_ahead,
            remote_ahead,
        )

        # Save current branch to restore after rebase
        _rc, current_ref, _ = await run_git(
            ["symbolic-ref", "--short", "HEAD"],
            cwd=repo_root,
            check=False,
        )
        original_branch = current_ref.strip() if _rc == 0 else ""

        # Checkout develop so we can rebase it
        rc_co, _, _ = await run_git(
            ["checkout", "develop"],
            cwd=repo_root,
            check=False,
        )
        if rc_co != 0:
            logger.warning(
                "Could not checkout develop for rebase. Using local as-is.",
            )
            return

        # Attempt rebase onto origin/develop
        rc_rb, _, stderr_rb = await run_git(
            ["rebase", "origin/develop"],
            cwd=repo_root,
            check=False,
        )
        if rc_rb == 0:
            # Rebase succeeded
            logger.info(
                "Rebased %d local commit(s) onto origin/develop successfully.",
                local_ahead,
            )
        else:
            # Rebase failed (conflicts) — attempt merge commit fallback
            await run_git(["rebase", "--abort"], cwd=repo_root, check=False)
            logger.info(
                "Rebase failed; attempting merge commit fallback.",
            )

            # Try merge commit without conflict resolution
            rc_merge, stdout_merge, stderr_merge = await run_git(
                ["merge", "--no-edit", "origin/develop"],
                cwd=repo_root,
                check=False,
            )
            if rc_merge == 0:
                # Merge succeeded
                logger.info(
                    "Merged origin/develop into local develop via merge commit.",
                )
            else:
                # Merge failed — abort and spawn merge agent (45-REQ-5.1)
                # Replaces blind -X ours strategy (45-REQ-6.2)
                await run_git(["merge", "--abort"], cwd=repo_root, check=False)
                logger.info(
                    "Merge commit failed; spawning merge agent to resolve conflicts.",
                )

                conflict_output = (
                    stderr_merge.strip() or stdout_merge.strip() or "merge conflict"
                )
                resolved = await run_merge_agent(
                    worktree_path=repo_root,
                    conflict_output=conflict_output,
                    model_id="ADVANCED",
                )
                if resolved:
                    # Agent resolved conflicts (45-REQ-5.2)
                    logger.info(
                        "Merge agent resolved develop-sync conflicts successfully.",
                    )
                else:
                    # Agent failed (45-REQ-5.E1) — log warning and leave as-is
                    logger.warning(
                        "Merge agent failed to resolve develop-sync conflicts. "
                        "Using local develop as-is; verify manually.",
                    )

        # Restore original branch
        if original_branch and original_branch != "develop":
            await run_git(
                ["checkout", original_branch],
                cwd=repo_root,
                check=False,
            )
        return

    # Local is behind only — fast-forward (19-REQ-1.6)
    logger.info(
        "Fast-forwarding local develop (%d commits behind origin/develop)",
        remote_ahead,
    )

    # Attempt fast-forward merge if on develop, else use branch force update
    rc_ff, _, _ = await run_git(
        ["merge", "--ff-only", "origin/develop"],
        cwd=repo_root,
        check=False,
    )
    if rc_ff != 0:
        # Fast-forward merge failed (maybe not on develop), try branch force update
        await run_git(
            ["branch", "-f", "develop", "origin/develop"],
            cwd=repo_root,
        )
