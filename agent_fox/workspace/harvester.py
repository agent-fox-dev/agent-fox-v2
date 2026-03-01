"""Harvester: integrate worktree changes into the development branch.

Requirements: 03-REQ-7.1 through 03-REQ-7.E2
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.workspace.worktree import WorkspaceInfo


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
    raise NotImplementedError
