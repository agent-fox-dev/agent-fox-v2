"""Git worktree lifecycle management: create and destroy isolated workspaces."""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from agent_fox.core.errors import WorkspaceError
from agent_fox.workspace.git import (
    branch_used_by_worktree,
    create_branch,
    delete_branch,
    run_git,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkspaceInfo:
    """Metadata about a created workspace."""

    path: Path
    branch: str
    spec_name: str
    task_group: int


def _cleanup_empty_ancestors(
    worktree_path: Path,
    root: Path,
) -> None:
    """Remove empty directories from worktree_path up to (not including) root.

    Walks upward from ``worktree_path``, removing directories that are empty.
    Stops when it reaches ``root`` (which is never removed), encounters a
    non-empty directory, or a removal fails.

    Errors are swallowed: ``PermissionError`` triggers a WARNING log, other
    ``OSError`` (e.g. directory not empty) silently stops traversal.

    Requirements: 80-REQ-3.1, 80-REQ-3.2, 80-REQ-3.E1, 80-REQ-3.E2
    """
    current = worktree_path
    while current != root:
        # Safety guard: never escape above root
        try:
            current.relative_to(root)
        except ValueError:
            break

        if not current.exists():
            current = current.parent
            continue

        try:
            current.rmdir()  # Only succeeds when the directory is empty
            logger.debug("Removed empty directory: %s", current)
        except PermissionError as exc:
            logger.warning("Failed to remove directory %s: %s", current, exc)
            break
        except OSError:
            # Directory is not empty or another OS error — stop traversal
            break

        current = current.parent


async def create_worktree(
    repo_root: Path,
    spec_name: str,
    task_group: int,
    base_branch: str = "develop",
    branch_name: str | None = None,
) -> WorkspaceInfo:
    """Create an isolated git worktree for a coding session.

    Creates a worktree at .agent-fox/worktrees/{spec_name}/{task_group}
    with a feature branch named feature/{spec_name}/{task_group}.

    When *branch_name* is provided it is used as the git branch instead
    of the default ``feature/{spec_name}/{task_group}`` convention. The
    worktree filesystem path is always derived from *spec_name* and
    *task_group* regardless of the branch name.

    If a stale worktree or branch exists, it is removed first.

    Requirements: 80-REQ-1.2, 80-REQ-3.2

    Raises:
        WorkspaceError: If worktree creation fails.
    """
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", spec_name):
        raise WorkspaceError(f"Invalid spec name: {spec_name!r}")

    worktrees_root = repo_root / ".agent-fox" / "worktrees"
    worktree_path = worktrees_root / spec_name / str(task_group)
    branch_name = branch_name or f"feature/{spec_name}/{task_group}"

    # Clean up orphaned empty sibling directories under the spec directory.
    # These are left over from prior crashed or partial cleanup runs.
    spec_dir = worktrees_root / spec_name
    if spec_dir.exists():
        for child in list(spec_dir.iterdir()):
            if child.is_dir() and not any(child.iterdir()):
                try:
                    child.rmdir()
                    logger.debug("Removed orphaned empty directory: %s", child)
                except OSError as exc:
                    logger.warning("Could not remove orphaned directory %s: %s", child, exc)

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
            shutil.rmtree(worktree_path, ignore_errors=True)

        # Clean up empty ancestor directories from the stale removal (80-REQ-3.2)
        _cleanup_empty_ancestors(worktree_path, worktrees_root)

    # Prune worktree registry to clean up any stale entries
    await run_git(["worktree", "prune"], cwd=repo_root, check=False)

    # Post-prune verification: ensure the branch is no longer referenced (80-REQ-1.2)
    still_referenced = await branch_used_by_worktree(repo_root, branch_name)
    if still_referenced:
        # Second prune attempt (80-REQ-1.E1)
        await run_git(["worktree", "prune"], cwd=repo_root, check=False)
        still_referenced = await branch_used_by_worktree(repo_root, branch_name)

    if still_referenced:
        logger.warning(
            "Branch '%s' is still referenced by a worktree after two prune attempts; skipping stale branch deletion",
            branch_name,
        )
    else:
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
    verifies the branch is no longer referenced, and deletes the feature
    branch. Cleans up empty ancestor directories.

    Does not raise if the worktree or branch is already gone.

    Requirements: 80-REQ-1.1, 80-REQ-1.E1, 80-REQ-3.1
    """
    worktrees_root = repo_root / ".agent-fox" / "worktrees"

    # 03-REQ-2.E1: If worktree path does not exist, treat removal as no-op
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

    # Post-prune verification: check if branch is still referenced (80-REQ-1.1)
    still_referenced = await branch_used_by_worktree(repo_root, workspace.branch)
    if still_referenced:
        # Second prune attempt (80-REQ-1.E1)
        await run_git(["worktree", "prune"], cwd=repo_root, check=False)
        still_referenced = await branch_used_by_worktree(repo_root, workspace.branch)

    if still_referenced:
        logger.warning(
            "Branch '%s' is still referenced by a worktree after two prune attempts; skipping branch deletion",
            workspace.branch,
        )
    else:
        # Delete the feature branch (03-REQ-2.E2: log warning if not found)
        await delete_branch(repo_root, workspace.branch, force=True)

    # Clean up empty ancestor directories (80-REQ-3.1)
    _cleanup_empty_ancestors(workspace.path, worktrees_root)
