"""Harvest and integrate worktree changes into the development branch.

Combines harvesting (rebase/merge into develop) with post-harvest remote
integration (push via local git).

Requirements: 03-REQ-7.1 through 03-REQ-7.E2,
              45-REQ-3.1, 45-REQ-4.1, 45-REQ-6.1,
              65-REQ-3.2, 65-REQ-3.3, 65-REQ-3.4, 65-REQ-3.5, 65-REQ-3.E2,
              78-REQ-1.1, 78-REQ-1.2, 78-REQ-1.3, 78-REQ-1.E1
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent_fox.core.errors import IntegrationError
from agent_fox.workspace import (
    WorkspaceInfo,
    _sync_develop_with_remote,
    abort_rebase,
    checkout_branch,
    get_changed_files,
    has_new_commits,
    merge_fast_forward,
    push_to_remote,
    rebase_onto,
    run_git,
)
from agent_fox.workspace.merge_agent import run_merge_agent
from agent_fox.workspace.merge_lock import MergeLock

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Harvest: integrate worktree changes into develop
# ---------------------------------------------------------------------------


async def harvest(
    repo_root: Path,
    workspace: WorkspaceInfo,
    dev_branch: str = "develop",
) -> list[str]:
    """Integrate a workspace's changes into the development branch.

    Steps:
    1. Check if the feature branch has new commits relative to
       dev_branch. If not, return an empty list (no-op).
    2. Checkout dev_branch in the main repo.
    3. Attempt a fast-forward merge of the feature branch.
    4. If fast-forward fails, rebase the feature branch onto
       dev_branch and retry the merge.
    5. If rebase fails, abort and raise IntegrationError.
    6. Return the list of changed files.

    Raises:
        IntegrationError: If merge fails after rebase retry.
    """
    # Step 1: Check for new commits (03-REQ-7.E2)
    if not await has_new_commits(repo_root, workspace.branch, dev_branch):
        logger.info(
            "No new commits on '%s' relative to '%s', skipping harvest",
            workspace.branch,
            dev_branch,
        )
        return []

    # Wrap all merge operations in the merge lock (45-REQ-3.1)
    lock = MergeLock(repo_root)
    async with lock:
        return await _harvest_under_lock(repo_root, workspace, dev_branch)


async def _clean_conflicting_untracked(
    repo_root: Path,
    feature_branch: str,
) -> None:
    """Remove untracked files that exist in the incoming feature branch.

    Git refuses to merge when untracked working-tree files would be
    overwritten. This finds the intersection of untracked files and
    files introduced by the feature branch, and removes them so the
    merge can proceed.

    Only removes files — never directories — and only those that would
    actually conflict with the merge.
    """
    # List untracked files in the repo root
    rc, stdout, _ = await run_git(
        ["ls-files", "--others", "--exclude-standard"],
        cwd=repo_root,
        check=False,
    )
    if rc != 0 or not stdout.strip():
        return

    untracked = set(stdout.strip().splitlines())
    if not untracked:
        return

    # List files that the feature branch would bring in
    rc, stdout, _ = await run_git(
        ["diff", "--name-only", "HEAD", feature_branch, "--"],
        cwd=repo_root,
        check=False,
    )
    if rc != 0 or not stdout.strip():
        return

    incoming = set(stdout.strip().splitlines())
    conflicts = untracked & incoming

    if not conflicts:
        return

    logger.info(
        "Removing %d untracked file(s) that would block merge: %s",
        len(conflicts),
        ", ".join(sorted(conflicts)[:5]),
    )
    for path in conflicts:
        full = repo_root / path
        try:
            full.unlink(missing_ok=True)
        except OSError:
            logger.debug("Could not remove untracked file %s", full)


async def _harvest_under_lock(
    repo_root: Path,
    workspace: WorkspaceInfo,
    dev_branch: str,
) -> list[str]:
    """Execute the harvest merge strategies under the merge lock.

    Called from harvest() after the lock is acquired.

    Requirements: 45-REQ-4.1, 45-REQ-6.1
    """
    # Ensure a clean working tree before any merge operation. A prior
    # failed harvest may have left tracked files dirty, which would cause
    # subsequent checkout/merge commands to fail.
    await run_git(["checkout", "--", "."], cwd=repo_root, check=False)

    # Remove untracked files that would block the merge. A prior session
    # may have created files (e.g. test files) that now exist both as
    # untracked in the working tree and in the incoming feature branch.
    await _clean_conflicting_untracked(repo_root, workspace.branch)

    # Capture the list of changed files before switching branches
    changed_files = await get_changed_files(
        repo_root,
        workspace.branch,
        dev_branch,
    )

    # Step 2: Checkout the development branch in the main repo
    await checkout_branch(repo_root, dev_branch)

    # Step 3: Attempt fast-forward merge (03-REQ-7.1)
    try:
        await merge_fast_forward(repo_root, workspace.branch)
        logger.info(
            "Fast-forward merge of '%s' into '%s' succeeded",
            workspace.branch,
            dev_branch,
        )
        return changed_files
    except IntegrationError:
        logger.info(
            "Fast-forward merge failed for '%s', attempting rebase",
            workspace.branch,
        )

    # Step 4: Rebase and retry (03-REQ-7.2)
    # Run rebase from the worktree directory because the feature branch
    # is checked out there. Using `git rebase <onto>` (without a branch
    # argument) rebases the currently checked-out branch.
    try:
        await rebase_onto(workspace.path, workspace.branch, dev_branch)
    except IntegrationError:
        # Rebase failed (conflicts) — abort and fall back to merge commit
        logger.info(
            "Rebase of '%s' onto '%s' had conflicts, falling back to merge commit",
            workspace.branch,
            dev_branch,
        )
        await abort_rebase(workspace.path)
        # Clean working tree in repo root — a failed rebase in the worktree
        # can leave tracked files dirty in the main repo, which blocks merge.
        await run_git(
            ["checkout", "--", "."],
            cwd=repo_root,
            check=False,
        )
        # Step 5: Fall back to regular merge (03-REQ-7.E1)
        # Run merge directly (not via merge_commit which auto-aborts on
        # failure). We need conflicts to remain so the merge agent can
        # resolve them.
        merge_rc, merge_stdout, merge_stderr = await run_git(
            ["merge", "--no-edit", "--", workspace.branch],
            cwd=repo_root,
            check=False,
        )
        if merge_rc != 0:
            # Step 6: Spawn merge agent to resolve conflicts (45-REQ-4.1)
            # Replaces blind -X theirs strategy (45-REQ-6.1)
            merge_detail = merge_stderr.strip() or merge_stdout.strip()
            logger.info(
                "Merge commit of '%s' failed, spawning merge agent to resolve conflicts",
                workspace.branch,
            )
            resolved = await run_merge_agent(
                worktree_path=repo_root,
                conflict_output=merge_detail,
                model_id="ADVANCED",
            )
            if not resolved:
                # Abort the failed merge and raise
                await run_git(
                    ["merge", "--abort"],
                    cwd=repo_root,
                    check=False,
                )
                raise IntegrationError(
                    f"Merge agent failed to resolve conflicts for '{workspace.branch}' into '{dev_branch}'",
                    branch=workspace.branch,
                )
        changed_files = await get_changed_files(
            repo_root,
            workspace.branch,
            dev_branch,
        )
        logger.info(
            "Merge commit of '%s' into '%s' succeeded",
            workspace.branch,
            dev_branch,
        )
        return changed_files

    # Retry the fast-forward merge after successful rebase
    # After rebase, the changed files may differ slightly, so re-fetch
    changed_files = await get_changed_files(
        repo_root,
        workspace.branch,
        dev_branch,
    )
    await merge_fast_forward(repo_root, workspace.branch)
    logger.info(
        "Merge of '%s' into '%s' succeeded after rebase",
        workspace.branch,
        dev_branch,
    )
    return changed_files


# ---------------------------------------------------------------------------
# Post-harvest remote integration: push changes, create PRs
# ---------------------------------------------------------------------------


async def _push_develop_if_pushable(repo_root: Path) -> None:
    """Push develop to origin, but only if the push won't be rejected.

    Checks whether origin/develop has commits not on local develop
    (which would cause a non-fast-forward rejection). If remote is ahead,
    attempts reconciliation via _sync_develop_with_remote() before pushing.
    If fetch fails during reconciliation, skips reconciliation and attempts
    push as-is.

    Requirements: 36-REQ-2.1, 36-REQ-2.2, 36-REQ-2.E1, 36-REQ-2.E2
    """
    _rc, remote_ahead_str, _ = await run_git(
        ["rev-list", "--count", "develop..origin/develop"],
        cwd=repo_root,
        check=False,
    )
    remote_ahead = int(remote_ahead_str.strip()) if remote_ahead_str.strip() else 0
    if remote_ahead > 0:
        # Origin is ahead — attempt reconciliation before push (36-REQ-2.1)
        logger.info(
            "origin/develop is %d commit(s) ahead. Attempting reconciliation before push.",
            remote_ahead,
        )
        try:
            await _sync_develop_with_remote(repo_root)
        except Exception as e:
            # If reconciliation fails (e.g., fetch failed), skip and attempt
            # push as-is (36-REQ-2.E2)
            logger.debug(
                "Reconciliation failed: %s. Skipping reconciliation and attempting push as-is.",
                e,
            )
        # Proceed to push regardless of reconciliation outcome (36-REQ-2.2)

    result = await push_to_remote(repo_root, "develop")
    if not result:
        # Log warning if push fails after reconciliation (36-REQ-2.E1)
        logger.warning("Failed to push develop to origin")


async def post_harvest_integrate(
    repo_root: Path,
    workspace: WorkspaceInfo,
) -> None:
    """Push develop to origin after harvest.

    Feature branches are kept local-only and are not pushed to the remote.
    The workspace parameter is retained for logging context.

    All remote operations are best-effort: failures are logged as warnings
    and never raised.

    Requirements: 65-REQ-3.2, 65-REQ-3.3, 65-REQ-3.4, 65-REQ-3.5,
                  65-REQ-3.E2, 78-REQ-1.1, 78-REQ-1.2, 78-REQ-1.3,
                  78-REQ-1.E1
    """
    # Push only develop — feature branches are local-only (78-REQ-1.1)
    await _push_develop_if_pushable(repo_root)
