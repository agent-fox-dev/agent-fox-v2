"""Git operations: branch management, merge, rebase, commit detection.

All operations are async and use ``asyncio.create_subprocess_exec`` to run git
commands without blocking the event loop.

Requirements: 03-REQ-9.1, 03-REQ-9.2, 19-REQ-1.1 through 19-REQ-1.6
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass
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
            logger.debug(
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
    force: bool = False,
) -> None:
    """Check out a branch in the given working directory.

    When *force* is True, uses ``git checkout -f`` to overwrite
    untracked files that would otherwise block the checkout (e.g.
    runtime artifacts created in the working directory that also
    exist on the target branch).

    Raises:
        WorkspaceError: If checkout fails.
    """
    cmd = ["checkout"]
    if force:
        cmd.append("-f")
    cmd.append(branch_name)
    await run_git(cmd, cwd=repo_path)


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
    cmd = ["merge", "--no-edit"]
    if strategy_option:
        cmd.extend(["-X", strategy_option])
    cmd.append(branch)

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


# ---------------------------------------------------------------------------
# New functions for 19-REQ-1.* (develop branch management)
# ---------------------------------------------------------------------------


async def local_branch_exists(repo_root: Path, branch: str) -> bool:
    """Check if a local branch exists.

    Requirements: 19-REQ-1.1
    """
    _rc, stdout, _stderr = await run_git(
        ["branch", "--list", branch],
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
        "Cannot determine default branch: no symbolic-ref, "
        "no local 'main' or 'master' branch found.",
    )


async def ensure_develop(repo_root: Path) -> None:
    """Ensure a local develop branch exists and is up-to-date.

    1. Fetch origin (warn and continue on failure).
    2. If local develop exists:
       a. If origin/develop exists and local is behind, fast-forward.
       b. If diverged, warn and use local as-is.
    3. If local develop does not exist:
       a. If origin/develop exists, create tracking branch.
       b. Otherwise, create from default branch.

    Raises:
        WorkspaceError: If no suitable base branch can be found.

    Requirements: 19-REQ-1.1, 19-REQ-1.2, 19-REQ-1.3, 19-REQ-1.5, 19-REQ-1.6
    """
    # Step 1: Fetch origin (best-effort)
    fetch_ok = True
    try:
        await run_git(["fetch", "origin"], cwd=repo_root)
    except WorkspaceError:
        logger.warning("Failed to fetch from origin; proceeding with local state only")
        fetch_ok = False

    has_local = await local_branch_exists(repo_root, "develop")

    if has_local:
        # Local develop exists — check if we need to fast-forward
        if fetch_ok:
            has_remote = await remote_branch_exists(repo_root, "develop")
            if has_remote:
                await _sync_develop_with_remote(repo_root)
        # 19-REQ-1.E1: local exists and is up-to-date → no-op
        logger.info("Local develop branch is ready")
        return

    # No local develop — need to create it
    if fetch_ok:
        has_remote = await remote_branch_exists(repo_root, "develop")
        if has_remote:
            # 19-REQ-1.2: Create from origin/develop
            await run_git(
                ["branch", "develop", "origin/develop"],
                cwd=repo_root,
            )
            logger.info("Created local develop branch tracking origin/develop")
            return

    # 19-REQ-1.3: No remote develop — create from default branch
    default_branch = await detect_default_branch(repo_root)
    await run_git(
        ["branch", "develop", default_branch],
        cwd=repo_root,
    )
    logger.info("Created local develop branch from '%s'", default_branch)


async def _sync_develop_with_remote(repo_root: Path) -> None:
    """Synchronize local develop with origin/develop.

    Checks commit counts to determine if local is behind, ahead,
    or diverged from remote. Fast-forwards if behind only.

    Requirements: 19-REQ-1.6, 19-REQ-1.E1, 19-REQ-1.E4
    """
    # Commits on remote not on local (remote is ahead)
    _rc, remote_ahead_str, _stderr = await run_git(
        ["rev-list", "--count", "develop..origin/develop"],
        cwd=repo_root,
        check=False,
    )
    remote_ahead = int(remote_ahead_str.strip()) if remote_ahead_str.strip() else 0

    # Commits on local not on remote (local is ahead)
    _rc, local_ahead_str, _stderr = await run_git(
        ["rev-list", "--count", "origin/develop..develop"],
        cwd=repo_root,
        check=False,
    )
    local_ahead = int(local_ahead_str.strip()) if local_ahead_str.strip() else 0

    if remote_ahead == 0:
        # Local is up-to-date or ahead — no-op (19-REQ-1.E1)
        return

    if local_ahead > 0 and remote_ahead > 0:
        # Diverged — attempt rebase to reconcile
        logger.info(
            "Local develop has diverged from origin/develop "
            "(%d local, %d remote commits). Attempting rebase.",
            local_ahead,
            remote_ahead,
        )

        # Save current branch to restore after rebase
        _rc, current_ref, _ = await run_git(
            ["symbolic-ref", "--short", "HEAD"],
            cwd=repo_root,
            check=False,
        )
        original_branch = current_ref.strip() if _rc == 0 else ""

        # Checkout develop so we can rebase it
        rc_co, _, _ = await run_git(
            ["checkout", "develop"],
            cwd=repo_root,
            check=False,
        )
        if rc_co != 0:
            logger.warning(
                "Could not checkout develop for rebase. Using local as-is.",
            )
            return

        # Attempt rebase onto origin/develop
        rc_rb, _, stderr_rb = await run_git(
            ["rebase", "origin/develop"],
            cwd=repo_root,
            check=False,
        )
        if rc_rb == 0:
            # Rebase succeeded
            logger.info(
                "Rebased %d local commit(s) onto origin/develop successfully.",
                local_ahead,
            )
        else:
            # Rebase failed (conflicts) — attempt merge commit fallback
            await run_git(["rebase", "--abort"], cwd=repo_root, check=False)
            logger.info(
                "Rebase failed; attempting merge commit fallback.",
            )

            # Try merge commit without conflict resolution
            rc_merge, _, _ = await run_git(
                ["merge", "--no-edit", "origin/develop"],
                cwd=repo_root,
                check=False,
            )
            if rc_merge == 0:
                # Merge succeeded
                logger.info(
                    "Merged origin/develop into local develop via merge commit.",
                )
            else:
                # Merge failed — abort and try merge with -X ours
                await run_git(["merge", "--abort"], cwd=repo_root, check=False)
                logger.info(
                    "Merge commit failed; attempting merge with -X ours strategy.",
                )

                # Try merge with -X ours (prefer local on conflicts)
                rc_ours, _, _ = await run_git(
                    ["merge", "-X", "ours", "--no-edit", "origin/develop"],
                    cwd=repo_root,
                    check=False,
                )
                if rc_ours == 0:
                    # Merge with -X ours succeeded
                    logger.warning(
                        "Merged origin/develop using -X ours strategy "
                        "(local changes preserved, remote changes may be discarded). "
                        "Verify reconciliation is correct."
                    )
                else:
                    # All strategies failed
                    await run_git(["merge", "--abort"], cwd=repo_root, check=False)
                    logger.warning(
                        "All reconciliation strategies "
                        "(rebase, merge, merge -X ours) failed. "
                        "Using local develop as-is; verify manually."
                    )

        # Restore original branch
        if original_branch and original_branch != "develop":
            await run_git(
                ["checkout", original_branch],
                cwd=repo_root,
                check=False,
            )
        return

    # Local is behind only — fast-forward (19-REQ-1.6)
    logger.info(
        "Fast-forwarding local develop (%d commits behind origin/develop)",
        remote_ahead,
    )

    # Attempt fast-forward merge if on develop, else use branch force update
    rc_ff, _, _ = await run_git(
        ["merge", "--ff-only", "origin/develop"],
        cwd=repo_root,
        check=False,
    )
    if rc_ff != 0:
        # Fast-forward merge failed (maybe not on develop), try branch force update
        await run_git(
            ["branch", "-f", "develop", "origin/develop"],
            cwd=repo_root,
        )


async def push_to_remote(
    repo_root: Path,
    branch: str,
    remote: str = "origin",
) -> bool:
    """Push a branch to the remote. Returns True on success, False on failure.

    Does not raise — logs a warning on failure.

    Requirements: 19-REQ-3.1
    """
    rc, _stdout, stderr = await run_git(
        ["push", remote, branch],
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


# ---------------------------------------------------------------------------
# Worktree manager (merged from worktree.py)
# ---------------------------------------------------------------------------


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
