"""Harvester: integrate worktree changes into the development branch.

Requirements: 03-REQ-7.1 through 03-REQ-7.E2
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent_fox.core.errors import IntegrationError
from agent_fox.workspace.git import (
    abort_rebase,
    checkout_branch,
    get_changed_files,
    has_new_commits,
    merge_commit,
    merge_fast_forward,
    rebase_onto,
)
from agent_fox.workspace.worktree import WorkspaceInfo

logger = logging.getLogger(__name__)


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
            "Rebase of '%s' onto '%s' had conflicts, "
            "falling back to merge commit",
            workspace.branch,
            dev_branch,
        )
        await abort_rebase(workspace.path)
        # Step 5: Fall back to regular merge (03-REQ-7.E1)
        await merge_commit(repo_root, workspace.branch)
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
