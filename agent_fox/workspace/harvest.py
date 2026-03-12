"""Harvest and integrate worktree changes into the development branch.

Combines harvesting (rebase/merge into develop) with post-harvest remote
integration (push, PR creation).

Requirements: 03-REQ-7.1 through 03-REQ-7.E2,
              19-REQ-3.1, 19-REQ-3.2, 19-REQ-3.3, 19-REQ-3.4,
              19-REQ-3.E1, 19-REQ-3.E2, 19-REQ-3.E3,
              19-REQ-4.E1, 19-REQ-4.E4,
              45-REQ-3.1, 45-REQ-4.1, 45-REQ-6.1
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from agent_fox.core.config import PlatformConfig
from agent_fox.core.errors import IntegrationError
from agent_fox.workspace.merge_agent import run_merge_agent
from agent_fox.workspace.merge_lock import MergeLock
from agent_fox.workspace.workspace import (
    WorkspaceInfo,
    _sync_develop_with_remote,
    abort_rebase,
    checkout_branch,
    get_changed_files,
    get_remote_url,
    has_new_commits,
    local_branch_exists,
    merge_commit,
    merge_fast_forward,
    push_to_remote,
    rebase_onto,
    run_git,
)

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


async def _harvest_under_lock(
    repo_root: Path,
    workspace: WorkspaceInfo,
    dev_branch: str,
) -> list[str]:
    """Execute the harvest merge strategies under the merge lock.

    Called from harvest() after the lock is acquired.

    Requirements: 45-REQ-4.1, 45-REQ-6.1
    """
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
        # Step 5: Fall back to regular merge (03-REQ-7.E1)
        try:
            await merge_commit(repo_root, workspace.branch)
        except IntegrationError as merge_err:
            # Step 6: Spawn merge agent to resolve conflicts (45-REQ-4.1)
            # Replaces blind -X theirs strategy (45-REQ-6.1)
            logger.info(
                "Merge commit of '%s' failed, spawning merge agent "
                "to resolve conflicts",
                workspace.branch,
            )
            conflict_output = str(merge_err)
            resolved = await run_merge_agent(
                worktree_path=repo_root,
                conflict_output=conflict_output,
                model_id="ADVANCED",
            )
            if not resolved:
                raise IntegrationError(
                    f"Merge agent failed to resolve conflicts for "
                    f"'{workspace.branch}' into '{dev_branch}'",
                    branch=workspace.branch,
                ) from merge_err
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
            "origin/develop is %d commit(s) ahead. "
            "Attempting reconciliation before push.",
            remote_ahead,
        )
        try:
            await _sync_develop_with_remote(repo_root)
        except Exception as e:
            # If reconciliation fails (e.g., fetch failed), skip and attempt
            # push as-is (36-REQ-2.E2)
            logger.debug(
                "Reconciliation failed: %s. Skipping reconciliation and "
                "attempting push as-is.",
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
    platform_config: PlatformConfig,
) -> None:
    """Push changes to remote after harvest.

    Behavior depends on platform configuration:
    - type="none": push develop to origin
    - type="github", auto_merge=true: push feature + push develop
    - type="github", auto_merge=false: push feature + create PR vs default branch

    All remote operations are best-effort: failures are logged as
    warnings and never raised.

    Requirements: 19-REQ-3.1, 19-REQ-3.2, 19-REQ-3.3, 19-REQ-3.4,
                  19-REQ-3.E1, 19-REQ-3.E2, 19-REQ-3.E3,
                  19-REQ-4.E1, 19-REQ-4.E4
    """
    from agent_fox.platform.github import GitHubPlatform, parse_github_remote

    feature_branch = workspace.branch

    if platform_config.type == "github":
        # Check for GITHUB_PAT — fall back to no-platform if missing
        token = os.environ.get("GITHUB_PAT")
        if not token:
            logger.warning(
                "GITHUB_PAT not set — falling back to pushing develop only",
            )
            # Fall back to no-platform behavior
            await _push_develop_if_pushable(repo_root)
            return

        # Parse remote URL for owner/repo
        remote_url = await get_remote_url(repo_root)
        if not remote_url:
            logger.warning(
                "Could not determine remote URL — falling back to pushing develop only",
            )
            await _push_develop_if_pushable(repo_root)
            return

        parsed = parse_github_remote(remote_url)
        if parsed is None:
            logger.warning(
                "Remote URL '%s' is not a GitHub URL"
                " — falling back to pushing develop only",
                remote_url,
            )
            await _push_develop_if_pushable(repo_root)
            return

        owner, repo = parsed

        # Push feature branch if it still exists locally (19-REQ-3.E3)
        if await local_branch_exists(repo_root, feature_branch):
            result = await push_to_remote(repo_root, feature_branch)
            if not result:
                logger.warning(
                    "Failed to push feature branch '%s' to origin",
                    feature_branch,
                )
        else:
            logger.warning(
                "Feature branch '%s' no longer exists locally — skipping push",
                feature_branch,
            )

        if platform_config.auto_merge:
            # 19-REQ-3.2: push develop too
            await _push_develop_if_pushable(repo_root)
        else:
            # 19-REQ-3.3: create PR, do NOT push develop
            platform = GitHubPlatform(owner=owner, repo=repo, token=token)
            try:
                spec = workspace.spec_name
                group = workspace.task_group
                pr_url = await platform.create_pr(
                    branch=feature_branch,
                    title=f"feat: {spec} task group {group}",
                    body=f"Automated PR for {spec} task group {group}.",
                )
                logger.info("Created PR: %s", pr_url)
            except Exception as exc:
                logger.warning(
                    "PR creation failed for '%s': %s",
                    feature_branch,
                    exc,
                )
    else:
        # 19-REQ-3.1: type="none" — just push develop
        await _push_develop_if_pushable(repo_root)
