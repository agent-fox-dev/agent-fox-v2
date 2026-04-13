"""Low-level async Git subprocess wrappers.

All operations use ``asyncio.create_subprocess_exec`` to run git
commands without blocking the event loop.

Requirements: 03-REQ-9.1, 03-REQ-9.2
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

from agent_fox.core.errors import IntegrationError, WorkspaceError

logger = logging.getLogger(__name__)

# Default timeout for git commands (seconds).  Remote operations
# (fetch, push, pull, clone, ls-remote) get a longer window.
_GIT_TIMEOUT = 60
_GIT_REMOTE_TIMEOUT = 120

_REMOTE_SUBCOMMANDS = frozenset(
    {
        "fetch",
        "push",
        "pull",
        "clone",
        "ls-remote",
    }
)

# Safe ref name pattern: alphanumeric, dots, underscores, hyphens, slashes, @.
# Rejects: leading dash, spaces, colons, tildes, carets, double-dots,
# backslashes, @{ sequences, and other characters unsafe in git refs.
_REF_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_./@-]*$")

# Pattern to extract the worktree path from a "used by worktree" error message.
# Example: "error: Cannot delete branch 'x' used by worktree at '/path'"
_WORKTREE_IN_USE_RE = re.compile(r"used by worktree at '([^']+)'")


def validate_ref_name(name: str) -> str:
    """Validate a git ref name to prevent argument injection.

    Rejects names that start with ``-`` (which git would interpret as
    flags), empty strings, and names containing characters unsafe in
    git refs (spaces, colons, tildes, carets, double-dots, backslashes,
    ``@{`` sequences).

    Returns the name unchanged if valid, raises WorkspaceError otherwise.
    """
    if not name or not _REF_NAME_RE.fullmatch(name) or ".." in name or "@{" in name:
        raise WorkspaceError(
            f"Invalid git ref name: {name!r}",
            ref_name=name,
        )
    return name


async def run_git(
    args: list[str],
    cwd: Path,
    check: bool = True,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr).

    When check=True and the command fails, raises WorkspaceError.

    Sets GIT_TERMINAL_PROMPT=0 to prevent credential prompts from
    hanging non-interactive sessions (e.g. expired PAT).
    """
    # Prevent interactive credential prompts from hanging the process.
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    if timeout is None:
        subcommand = args[0] if args else ""
        timeout = _GIT_REMOTE_TIMEOUT if subcommand in _REMOTE_SUBCOMMANDS else _GIT_TIMEOUT

    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        cmd_str = " ".join(["git", *args])
        subcommand = args[0] if args else "unknown"
        logger.error("git %s timed out after %ds: %s", subcommand, timeout, cmd_str)
        sanitized_msg = f"git {subcommand} timed out after {timeout}s"
        if check:
            raise WorkspaceError(sanitized_msg, command=cmd_str, returncode=-1)
        return -1, "", sanitized_msg

    stdout = stdout_bytes.decode()
    stderr = stderr_bytes.decode()
    returncode = proc.returncode or 0

    if check and returncode != 0:
        cmd_str = " ".join(["git", *args])
        subcommand = args[0] if args else "unknown"
        logger.debug("git %s failed (rc=%d): %s", subcommand, returncode, stderr.strip())
        raise WorkspaceError(
            f"git {subcommand} failed (exit code {returncode})",
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
        WorkspaceError: If branch creation fails or ref names are invalid.
    """
    validate_ref_name(branch_name)
    validate_ref_name(start_point)
    await run_git(["branch", "--", branch_name, start_point], cwd=repo_path)


async def branch_used_by_worktree(
    repo_root: Path,
    branch: str,
) -> bool:
    """Check if a branch is referenced by any git worktree.

    Parses ``git worktree list --porcelain`` output. Returns ``True`` if
    the branch appears in any worktree's ``branch`` line, ``False`` if not
    found. Returns ``False`` (optimistic fallback) if the command fails.

    Requirements: 80-REQ-1.3, 80-REQ-1.E2
    """
    try:
        _rc, stdout, _stderr = await run_git(
            ["worktree", "list", "--porcelain"],
            cwd=repo_root,
            check=False,
        )
    except Exception:
        logger.warning("git worktree list --porcelain failed; proceeding optimistically")
        return False

    target = f"refs/heads/{branch}"
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("branch ") and stripped[len("branch ") :] == target:
            return True
    return False


async def _resolve_worktree_conflict(
    repo_path: Path,
    stderr: str,
    retry_args: list[str],
    live_error_msg: str,
) -> tuple[int, str]:
    """Handle a "used by worktree" git error: prune stale entries and retry.

    If the worktree directory exists on disk (live), raises WorkspaceError.
    If the directory is gone (stale entry), prunes worktree metadata and
    retries the command once.

    Returns (returncode, stderr) of the retry attempt.

    Requirements: 80-REQ-2.1, 80-REQ-2.E1
    """
    match = _WORKTREE_IN_USE_RE.search(stderr)
    worktree_path = Path(match.group(1)) if match else None

    if worktree_path is not None and worktree_path.exists():
        raise WorkspaceError(live_error_msg, branch=retry_args[-1])

    logger.debug(
        "Git command blocked by stale worktree entry; pruning and retrying",
    )
    await run_git(["worktree", "prune"], cwd=repo_path, check=False)
    rc2, _stdout2, stderr2 = await run_git(
        retry_args,
        cwd=repo_path,
        check=False,
    )
    return rc2, stderr2


async def delete_branch(
    repo_path: Path,
    branch_name: str,
    force: bool = False,
) -> None:
    """Delete a local git branch.

    Logs a warning and returns if the branch does not exist.

    MODIFIED (80-REQ-2.1, 80-REQ-2.2, 80-REQ-2.E1): If deletion fails with
    "used by worktree", extracts the worktree path from the error message.
    - If the path exists on the filesystem (live worktree), raises WorkspaceError.
    - If the path does not exist (stale entry), prunes and retries once.
    - If the retry also fails, logs a warning and returns without raising.

    Raises:
        WorkspaceError: If deletion fails for reasons other than the branch
            not existing, or if the branch is used by a live (existing) worktree.
    """
    validate_ref_name(branch_name)
    flag = "-D" if force else "-d"
    retry_args = ["branch", flag, "--", branch_name]
    returncode, _stdout, stderr = await run_git(
        retry_args,
        cwd=repo_path,
        check=False,
    )
    if returncode != 0:
        # Branch does not exist -- treat as no-op
        if "not found" in stderr or "error: branch" in stderr:
            logger.debug(
                "Branch '%s' does not exist, skipping deletion",
                branch_name,
            )
            return

        if "used by worktree" in stderr:
            rc2, stderr2 = await _resolve_worktree_conflict(
                repo_path,
                stderr,
                retry_args,
                f"Branch '{branch_name}' is in use by a live worktree; cannot delete",
            )
            if rc2 != 0:
                # Retry also failed — non-fatal, log warning and return (80-REQ-2.2)
                logger.warning(
                    "Failed to delete branch '%s' after pruning stale worktrees: %s",
                    branch_name,
                    stderr2.strip() or stderr.strip(),
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

    If checkout fails because the branch is held by another worktree:
    - If the worktree directory is stale (doesn't exist on disk), prunes
      worktree entries and retries once.
    - If the worktree directory is live (exists on disk), raises
      WorkspaceError with a clear message.

    Raises:
        WorkspaceError: If checkout fails or ref name is invalid.
    """
    validate_ref_name(branch_name)
    retry_args = ["checkout", branch_name]
    returncode, _stdout, stderr = await run_git(
        retry_args,
        cwd=repo_path,
        check=False,
    )
    if returncode == 0:
        return

    if "used by worktree" in stderr:
        rc2, _stderr2 = await _resolve_worktree_conflict(
            repo_path,
            stderr,
            retry_args,
            f"Cannot checkout '{branch_name}': branch is in use by a live worktree",
        )
        if rc2 == 0:
            return
        raise WorkspaceError(
            f"git checkout failed (exit code {rc2})",
            command=f"git checkout {branch_name}",
            returncode=rc2,
        )

    raise WorkspaceError(
        f"git checkout failed (exit code {returncode})",
        command=f"git checkout {branch_name}",
        returncode=returncode,
    )


async def has_new_commits(
    repo_path: Path,
    branch: str,
    base: str,
) -> bool:
    """Check if branch has commits not in base.

    Returns True if there are commits on ``branch`` that are not
    reachable from ``base``.
    """
    validate_ref_name(branch)
    validate_ref_name(base)
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
    validate_ref_name(branch)
    validate_ref_name(base)
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
    validate_ref_name(branch)
    returncode, _stdout, stderr = await run_git(
        ["merge", "--ff-only", "--", branch],
        cwd=repo_path,
        check=False,
    )
    if returncode != 0:
        raise IntegrationError(
            f"Fast-forward merge of '{branch}' failed: {stderr.strip()}",
            branch=branch,
        )


async def merge_commit(
    repo_path: Path,
    branch: str,
    *,
    strategy_option: str | None = None,
) -> None:
    """Merge branch into HEAD with a merge commit.

    Falls back to a regular (non-fast-forward) merge when a
    fast-forward is not possible.

    Args:
        strategy_option: If set, passed as ``-X {value}`` to git merge
            (e.g. ``"theirs"`` to auto-resolve conflicts by preferring
            the incoming branch).

    Raises:
        IntegrationError: If the merge fails (conflicts).
    """
    validate_ref_name(branch)
    cmd = ["merge", "--no-edit"]
    if strategy_option:
        cmd.extend(["-X", strategy_option])
    cmd.extend(["--", branch])

    returncode, stdout, stderr = await run_git(
        cmd,
        cwd=repo_path,
        check=False,
    )
    if returncode != 0:
        # Abort the failed merge to leave the repo in a clean state
        await run_git(["merge", "--abort"], cwd=repo_path, check=False)
        # git merge writes conflict details to stdout, not stderr
        detail = stderr.strip() or stdout.strip()
        raise IntegrationError(
            f"Merge of '{branch}' failed: {detail}",
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
    validate_ref_name(branch)
    validate_ref_name(onto)
    returncode, stdout, stderr = await run_git(
        ["rebase", onto, branch],
        cwd=repo_path,
        check=False,
    )
    if returncode != 0:
        # git rebase may write conflict details to stdout or stderr
        detail = stderr.strip() or stdout.strip()
        raise IntegrationError(
            f"Rebase of '{branch}' onto '{onto}' failed: {detail}",
            branch=branch,
            onto=onto,
        )


async def abort_rebase(repo_path: Path) -> None:
    """Abort an in-progress rebase."""
    await run_git(["rebase", "--abort"], cwd=repo_path, check=False)


async def local_branch_exists(repo_root: Path, branch: str) -> bool:
    """Check if a local branch exists.

    Requirements: 19-REQ-1.1
    """
    validate_ref_name(branch)
    _rc, stdout, _stderr = await run_git(
        ["branch", "--list", "--", branch],
        cwd=repo_root,
        check=False,
    )
    return branch in stdout


async def remote_branch_exists(
    repo_root: Path,
    branch: str,
    remote: str = "origin",
) -> bool:
    """Check if a branch exists on the given remote.

    Requirements: 19-REQ-1.1
    """
    validate_ref_name(branch)
    _rc, stdout, _stderr = await run_git(
        ["ls-remote", "--heads", remote, branch],
        cwd=repo_root,
        check=False,
    )
    return bool(stdout.strip())


async def detect_default_branch(repo_root: Path) -> str:
    """Detect the repository's default branch name.

    Tries git symbolic-ref refs/remotes/origin/HEAD, then falls back
    to 'main', then 'master'. Returns the first that exists locally.

    Raises:
        WorkspaceError: If no default branch can be determined.

    Requirements: 19-REQ-1.4
    """
    # Try symbolic-ref first
    rc, stdout, _stderr = await run_git(
        ["symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=repo_root,
        check=False,
    )
    if rc == 0 and stdout.strip():
        # e.g. "refs/remotes/origin/main" -> "main"
        ref = stdout.strip()
        branch_name = ref.split("/")[-1]
        return branch_name

    # Fallback: check local main, then master
    for candidate in ("main", "master"):
        if await local_branch_exists(repo_root, candidate):
            return candidate

    raise WorkspaceError(
        "Cannot determine default branch: no symbolic-ref, no local 'main' or 'master' branch found.",
    )


async def push_to_remote(
    repo_root: Path,
    branch: str,
    remote: str = "origin",
    *,
    force: bool = False,
) -> bool:
    """Push a branch to the remote. Returns True on success, False on failure.

    When ``force=True``, uses ``--force`` to overwrite the remote branch even
    if the push is not a fast-forward.

    Does not raise — logs a warning on failure.

    Requirements: 19-REQ-3.1, 93-REQ-3.2
    """
    validate_ref_name(branch)
    args = ["push"]
    if force:
        args.append("--force")
    args.extend([remote, branch])
    rc, _stdout, stderr = await run_git(
        args,
        cwd=repo_root,
        check=False,
    )
    if rc != 0:
        logger.warning(
            "Failed to push '%s' to '%s': %s",
            branch,
            remote,
            stderr.strip(),
        )
        return False
    logger.info("Pushed '%s' to '%s'", branch, remote)
    return True


async def get_remote_url(
    repo_root: Path,
    remote: str = "origin",
) -> str | None:
    """Get the URL of a git remote.

    Returns the remote URL string, or None if the remote is not configured.
    """
    rc, stdout, _stderr = await run_git(
        ["remote", "get-url", remote],
        cwd=repo_root,
        check=False,
    )
    if rc != 0:
        return None
    return stdout.strip() or None
