"""Git operations: branch management, merge, rebase, commit detection.

All operations are async and use ``asyncio.create_subprocess_exec`` to run git
commands without blocking the event loop.

Requirements: 03-REQ-9.1, 03-REQ-9.2
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from agent_fox.core.errors import IntegrationError, WorkspaceError

logger = logging.getLogger(__name__)


async def run_git(
    args: list[str],
    cwd: Path,
    check: bool = True,
) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr).

    When check=True and the command fails, raises WorkspaceError.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    stdout = stdout_bytes.decode()
    stderr = stderr_bytes.decode()
    returncode = proc.returncode or 0

    if check and returncode != 0:
        cmd_str = " ".join(["git", *args])
        raise WorkspaceError(
            f"git command failed: {cmd_str}\n{stderr.strip()}",
            command=cmd_str,
            returncode=returncode,
        )

    return returncode, stdout, stderr


async def create_branch(
    repo_path: Path,
    branch_name: str,
    start_point: str,
) -> None:
    """Create a new git branch at the given start point.

    Raises:
        WorkspaceError: If branch creation fails.
    """
    await run_git(["branch", branch_name, start_point], cwd=repo_path)


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
    flag = "-D" if force else "-d"
    returncode, _stdout, stderr = await run_git(
        ["branch", flag, branch_name],
        cwd=repo_path,
        check=False,
    )
    if returncode != 0:
        # Branch does not exist -- treat as no-op
        if "not found" in stderr or "error: branch" in stderr:
            logger.warning(
                "Branch '%s' does not exist, skipping deletion",
                branch_name,
            )
            return
        # Some other failure
        raise WorkspaceError(
            f"Failed to delete branch '{branch_name}': {stderr.strip()}",
            branch=branch_name,
        )


async def checkout_branch(
    repo_path: Path,
    branch_name: str,
) -> None:
    """Check out a branch in the given working directory.

    Raises:
        WorkspaceError: If checkout fails.
    """
    await run_git(["checkout", branch_name], cwd=repo_path)


async def has_new_commits(
    repo_path: Path,
    branch: str,
    base: str,
) -> bool:
    """Check if branch has commits not in base.

    Returns True if there are commits on ``branch`` that are not
    reachable from ``base``.
    """
    _rc, stdout, _stderr = await run_git(
        ["rev-list", "--count", f"{base}..{branch}"],
        cwd=repo_path,
    )
    return int(stdout.strip()) > 0


async def get_changed_files(
    repo_path: Path,
    branch: str,
    base: str,
) -> list[str]:
    """Return list of files changed between base and branch."""
    _rc, stdout, _stderr = await run_git(
        ["diff", "--name-only", base, branch],
        cwd=repo_path,
    )
    return [f for f in stdout.strip().split("\n") if f]


async def merge_fast_forward(
    repo_path: Path,
    branch: str,
) -> None:
    """Attempt a fast-forward-only merge of branch into HEAD.

    Raises:
        IntegrationError: If fast-forward is not possible.
    """
    returncode, _stdout, stderr = await run_git(
        ["merge", "--ff-only", branch],
        cwd=repo_path,
        check=False,
    )
    if returncode != 0:
        raise IntegrationError(
            f"Fast-forward merge of '{branch}' failed: {stderr.strip()}",
            branch=branch,
        )


async def rebase_onto(
    repo_path: Path,
    branch: str,
    onto: str,
) -> None:
    """Rebase branch onto the given target.

    Raises:
        IntegrationError: If rebase fails (conflicts).
    """
    returncode, _stdout, stderr = await run_git(
        ["rebase", onto, branch],
        cwd=repo_path,
        check=False,
    )
    if returncode != 0:
        raise IntegrationError(
            f"Rebase of '{branch}' onto '{onto}' failed: {stderr.strip()}",
            branch=branch,
            onto=onto,
        )


async def abort_rebase(repo_path: Path) -> None:
    """Abort an in-progress rebase."""
    await run_git(["rebase", "--abort"], cwd=repo_path, check=False)
