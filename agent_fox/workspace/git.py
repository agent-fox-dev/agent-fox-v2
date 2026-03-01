"""Git operations: branch management, merge, rebase, commit detection.

Requirements: 03-REQ-9.1, 03-REQ-9.2
"""

from __future__ import annotations

from pathlib import Path


async def run_git(
    args: list[str],
    cwd: Path,
    check: bool = True,
) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr).

    When check=True and the command fails, raises WorkspaceError.
    """
    raise NotImplementedError


async def create_branch(
    repo_path: Path,
    branch_name: str,
    start_point: str,
) -> None:
    """Create a new git branch at the given start point.

    Raises:
        WorkspaceError: If branch creation fails.
    """
    raise NotImplementedError


async def delete_branch(
    repo_path: Path,
    branch_name: str,
    force: bool = False,
) -> None:
    """Delete a local git branch.

    Logs a warning and returns if the branch does not exist.

    Raises:
        WorkspaceError: If deletion fails for reasons other than
            the branch not existing.
    """
    raise NotImplementedError


async def checkout_branch(
    repo_path: Path,
    branch_name: str,
) -> None:
    """Check out a branch in the given working directory.

    Raises:
        WorkspaceError: If checkout fails.
    """
    raise NotImplementedError


async def has_new_commits(
    repo_path: Path,
    branch: str,
    base: str,
) -> bool:
    """Check if branch has commits not in base.

    Returns True if there are commits on `branch` that are not
    reachable from `base`.
    """
    raise NotImplementedError


async def get_changed_files(
    repo_path: Path,
    branch: str,
    base: str,
) -> list[str]:
    """Return list of files changed between base and branch."""
    raise NotImplementedError


async def merge_fast_forward(
    repo_path: Path,
    branch: str,
) -> None:
    """Attempt a fast-forward-only merge of branch into HEAD.

    Raises:
        IntegrationError: If fast-forward is not possible.
    """
    raise NotImplementedError


async def rebase_onto(
    repo_path: Path,
    branch: str,
    onto: str,
) -> None:
    """Rebase branch onto the given target.

    Raises:
        IntegrationError: If rebase fails (conflicts).
    """
    raise NotImplementedError


async def abort_rebase(repo_path: Path) -> None:
    """Abort an in-progress rebase."""
    raise NotImplementedError
