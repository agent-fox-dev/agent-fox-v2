"""Develop branch management: ensure, sync, and reconcile.

Requirements: 19-REQ-1.1 through 19-REQ-1.6,
              45-REQ-3.2, 45-REQ-5.1, 45-REQ-5.2, 45-REQ-5.E1, 45-REQ-6.2,
              118-REQ-5.1, 118-REQ-5.2, 118-REQ-5.3, 118-REQ-5.E1
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent_fox.core.errors import WorkspaceError
from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.knowledge.audit import AuditEventType, AuditSeverity
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

    Requirements: 19-REQ-1.1, 19-REQ-1.2, 19-REQ-1.3, 19-REQ-1.5, 19-REQ-1.6,
                  118-REQ-5.E1
    """
    # Step 1: Fetch origin (best-effort)
    fetch_ok = True
    try:
        await run_git(["fetch", "origin"], cwd=repo_root)
    except WorkspaceError as exc:
        logger.warning("Failed to fetch from origin; proceeding with local state only")
        fetch_ok = False
        # 118-REQ-5.E1: emit develop.fetch_failed audit event
        emit_audit_event(
            None,
            "",
            AuditEventType.DEVELOP_FETCH_FAILED,
            severity=AuditSeverity.WARNING,
            payload={"reason": str(exc)},
        )

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


async def _sync_develop_with_remote(repo_root: Path) -> str | None:
    """Synchronize local develop with origin/develop.

    Checks commit counts to determine if local is behind, ahead,
    or diverged from remote. Fast-forwards if behind only.

    Read-only divergence checks are performed without the lock.
    The merge lock is only acquired when actual changes are needed
    (45-REQ-3.2).

    Returns the sync method used on success ('fast-forward', 'rebase',
    'merge', or 'merge-agent'), or None when no sync was needed or it
    failed.

    Requirements: 19-REQ-1.6, 19-REQ-1.E1, 19-REQ-1.E4,
                  45-REQ-3.2, 45-REQ-5.1, 45-REQ-5.2, 45-REQ-5.E1, 45-REQ-6.2
    """
    # Read-only divergence checks — no lock needed
    _rc, remote_ahead_str, _stderr = await run_git(
        ["rev-list", "--count", "develop..origin/develop"],
        cwd=repo_root,
        check=False,
    )
    remote_ahead = int(remote_ahead_str.strip()) if remote_ahead_str.strip() else 0

    _rc, local_ahead_str, _stderr = await run_git(
        ["rev-list", "--count", "origin/develop..develop"],
        cwd=repo_root,
        check=False,
    )
    local_ahead = int(local_ahead_str.strip()) if local_ahead_str.strip() else 0

    if remote_ahead == 0:
        # Local is up-to-date or ahead — nothing to do (19-REQ-1.E1)
        return None

    # Remote has new commits — acquire lock before making changes (45-REQ-3.2)
    lock = MergeLock(repo_root)
    async with lock:
        return await _sync_develop_under_lock(repo_root, remote_ahead, local_ahead)


async def _sync_develop_under_lock(
    repo_root: Path, remote_ahead: int, local_ahead: int
) -> str | None:
    """Execute the develop sync strategies under the merge lock.

    Called from _sync_develop_with_remote() after the lock is acquired.
    The commit counts are pre-computed outside the lock.

    Returns the sync method used on success ('fast-forward', 'rebase',
    'merge', or 'merge-agent'), or None on failure.

    Requirements: 118-REQ-5.1, 118-REQ-5.2, 118-REQ-5.3
    """
    sync_method: str | None = None

    if local_ahead > 0 and remote_ahead > 0:
        # Diverged — attempt rebase to reconcile
        # 118-REQ-5.3: log commit counts at INFO before reconciliation
        logger.info(
            "Local develop has diverged from origin/develop (%d local, %d remote commits). Attempting rebase.",
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
            # 118-REQ-5.2: emit develop.sync_failed audit event
            emit_audit_event(
                None,
                "",
                AuditEventType.DEVELOP_SYNC_FAILED,
                severity=AuditSeverity.WARNING,
                payload={
                    "reason": "Could not checkout develop for rebase",
                    "local_ahead": local_ahead,
                    "remote_ahead": remote_ahead,
                },
            )
            return None

        # Attempt rebase onto origin/develop
        rc_rb, _, stderr_rb = await run_git(
            ["rebase", "origin/develop"],
            cwd=repo_root,
            check=False,
        )
        if rc_rb == 0:
            # Rebase succeeded
            sync_method = "rebase"
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
                sync_method = "merge"
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

                conflict_output = stderr_merge.strip() or stdout_merge.strip() or "merge conflict"
                resolved = await run_merge_agent(
                    worktree_path=repo_root,
                    conflict_output=conflict_output,
                    model_id="ADVANCED",
                )
                if resolved:
                    # Agent resolved conflicts (45-REQ-5.2)
                    sync_method = "merge-agent"
                    logger.info(
                        "Merge agent resolved develop-sync conflicts successfully.",
                    )
                else:
                    # Agent failed (45-REQ-5.E1) — log warning and leave as-is
                    logger.warning(
                        "Merge agent failed to resolve develop-sync conflicts. "
                        "Using local develop as-is; verify manually.",
                    )
                    # 118-REQ-5.2: emit develop.sync_failed audit event
                    emit_audit_event(
                        None,
                        "",
                        AuditEventType.DEVELOP_SYNC_FAILED,
                        severity=AuditSeverity.WARNING,
                        payload={
                            "reason": "Merge agent failed to resolve conflicts",
                            "local_ahead": local_ahead,
                            "remote_ahead": remote_ahead,
                        },
                    )
                    # Restore original branch
                    if original_branch and original_branch != "develop":
                        await run_git(
                            ["checkout", original_branch],
                            cwd=repo_root,
                            check=False,
                        )
                    return None

        # Restore original branch
        if original_branch and original_branch != "develop":
            await run_git(
                ["checkout", original_branch],
                cwd=repo_root,
                check=False,
            )

        # 118-REQ-5.1: emit develop.sync audit event on success
        if sync_method is not None:
            emit_audit_event(
                None,
                "",
                AuditEventType.DEVELOP_SYNC,
                payload={
                    "method": sync_method,
                    "local_ahead": local_ahead,
                    "remote_ahead": remote_ahead,
                },
            )
        return sync_method

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

    sync_method = "fast-forward"

    # 118-REQ-5.1: emit develop.sync audit event on success
    emit_audit_event(
        None,
        "",
        AuditEventType.DEVELOP_SYNC,
        payload={
            "method": sync_method,
            "local_ahead": local_ahead,
            "remote_ahead": remote_ahead,
        },
    )
    return sync_method
