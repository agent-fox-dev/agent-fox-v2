"""Worktree manager: create and destroy isolated git worktrees.

Requirements: 03-REQ-1.1 through 03-REQ-1.E3, 03-REQ-2.1 through 03-REQ-2.E2
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_fox.workspace.git import run_git  # noqa: F401


@dataclass(frozen=True)
class WorkspaceInfo:
    """Metadata about a created workspace."""

    path: Path
    branch: str
    spec_name: str
    task_group: int


async def create_worktree(
    repo_root: Path,
    spec_name: str,
    task_group: int,
    base_branch: str = "develop",
) -> WorkspaceInfo:
    """Create an isolated git worktree for a coding session.

    Creates a worktree at .agent-fox/worktrees/{spec_name}/{task_group}
    with a feature branch named feature/{spec_name}/{task_group}.

    If a stale worktree or branch exists, it is removed first.

    Raises:
        WorkspaceError: If worktree creation fails.
    """
    raise NotImplementedError


async def destroy_worktree(
    repo_root: Path,
    workspace: WorkspaceInfo,
) -> None:
    """Remove a git worktree and its feature branch.

    Removes the worktree directory, prunes the worktree registry,
    and deletes the feature branch. Cleans up empty spec directories.

    Does not raise if the worktree or branch is already gone.
    """
    raise NotImplementedError
