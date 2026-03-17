"""Git worktree lifecycle management: create and destroy isolated workspaces."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from agent_fox.workspace.git import create_branch, delete_branch, run_git

logger = logging.getLogger(__name__)


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
    worktree_path = repo_root / ".agent-fox" / "worktrees" / spec_name / str(task_group)
    branch_name = f"feature/{spec_name}/{task_group}"

    # Clean up stale worktree if it exists (03-REQ-1.E1)
    if worktree_path.exists():
        logger.info("Removing stale worktree at %s", worktree_path)
        await run_git(
            ["worktree", "remove", "--force", str(worktree_path)],
            cwd=repo_root,
            check=False,
        )
        # If git worktree remove didn't fully clean up, remove manually
        if worktree_path.exists():
            shutil.rmtree(worktree_path)

    # Prune worktree registry to clean up any stale entries
    await run_git(["worktree", "prune"], cwd=repo_root, check=False)

    # Clean up stale feature branch if it exists (03-REQ-1.E2)
    await delete_branch(repo_root, branch_name, force=True)

    # Create the feature branch from the base branch tip
    await create_branch(repo_root, branch_name, base_branch)

    # Ensure parent directory exists
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # Create the worktree with the feature branch checked out
    await run_git(
        ["worktree", "add", str(worktree_path), branch_name],
        cwd=repo_root,
    )

    return WorkspaceInfo(
        path=worktree_path,
        branch=branch_name,
        spec_name=spec_name,
        task_group=task_group,
    )


async def destroy_worktree(
    repo_root: Path,
    workspace: WorkspaceInfo,
) -> None:
    """Remove a git worktree and its feature branch.

    Removes the worktree directory, prunes the worktree registry,
    and deletes the feature branch. Cleans up empty spec directories.

    Does not raise if the worktree or branch is already gone.
    """
    # 03-REQ-2.E1: If worktree path does not exist, treat as no-op
    if workspace.path.exists():
        # Remove the worktree via git
        await run_git(
            ["worktree", "remove", "--force", str(workspace.path)],
            cwd=repo_root,
            check=False,
        )
        # If git worktree remove didn't fully clean up, remove manually
        if workspace.path.exists():
            shutil.rmtree(workspace.path, ignore_errors=True)

    # Prune worktree registry
    await run_git(["worktree", "prune"], cwd=repo_root, check=False)

    # Delete the feature branch (03-REQ-2.E2: log warning if not found)
    await delete_branch(repo_root, workspace.branch, force=True)

    # Clean up empty spec directory under worktrees (03-REQ-2.2)
    spec_dir = repo_root / ".agent-fox" / "worktrees" / workspace.spec_name
    if spec_dir.exists() and not any(spec_dir.iterdir()):
        spec_dir.rmdir()
        logger.info("Removed empty spec directory: %s", spec_dir)
