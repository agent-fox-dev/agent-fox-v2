"""Harvest and integrate worktree changes into the development branch.

Combines harvesting (rebase/merge into develop) with post-harvest remote
integration (push via local git).

Requirements: 03-REQ-7.1 through 03-REQ-7.E2,
              45-REQ-3.1, 45-REQ-4.1, 45-REQ-6.1,
              65-REQ-3.2, 65-REQ-3.3, 65-REQ-3.4, 65-REQ-3.5, 65-REQ-3.E2,
              78-REQ-1.1, 78-REQ-1.2, 78-REQ-1.3, 78-REQ-1.E1
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent_fox.core.errors import IntegrationError
from agent_fox.workspace import (
    WorkspaceInfo,
    _sync_develop_with_remote,
    checkout_branch,
    get_changed_files,
    has_new_commits,
    push_to_remote,
    run_git,
)
from agent_fox.workspace.merge_agent import run_merge_agent
from agent_fox.workspace.merge_lock import MergeLock

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

    Always uses ``git merge --squash`` to produce a single commit on
    dev_branch, regardless of the feature branch topology.

    Steps:
    1. Check if the feature branch has new commits relative to
       dev_branch. If not, return an empty list (no-op).
    2. Checkout dev_branch in the main repo.
    3. Squash-merge the feature branch (single commit, no merge commit).
    4. On conflict, spawn the merge agent to resolve.
    5. Return the list of changed files.

    Raises:
        IntegrationError: If merge fails after merge-agent attempt.
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


async def _clean_conflicting_untracked(
    repo_root: Path,
    feature_branch: str,
) -> None:
    """Remove untracked files that exist in the incoming feature branch.

    Git refuses to merge when untracked working-tree files would be
    overwritten.  This finds the intersection of untracked files and
    files introduced by the feature branch, then removes them *only*
    when their on-disk content is identical to the branch version.

    If any conflicting untracked file has content that differs from the
    branch version (i.e. local work not yet committed), the function
    raises IntegrationError rather than silently destroying that work.

    If content cannot be verified (git error, unreadable file), the
    file is preserved and a WARNING is logged.

    Only removes files — never directories — and only those that would
    actually conflict with the merge.

    Raises:
        IntegrationError: If any conflicting untracked file has content
            that diverges from the feature branch version.
    """
    # List untracked files in the repo root
    rc, stdout, _ = await run_git(
        ["ls-files", "--others", "--exclude-standard"],
        cwd=repo_root,
        check=False,
    )
    if rc != 0 or not stdout.strip():
        return

    untracked = set(stdout.strip().splitlines())
    if not untracked:
        return

    # List files that the feature branch would bring in
    rc, stdout, _ = await run_git(
        ["diff", "--name-only", "HEAD", feature_branch, "--"],
        cwd=repo_root,
        check=False,
    )
    if rc != 0 or not stdout.strip():
        return

    incoming = set(stdout.strip().splitlines())
    conflicts = untracked & incoming

    if not conflicts:
        return

    safe_to_remove: list[str] = []
    divergent: list[str] = []
    unverifiable: list[str] = []

    for path in sorted(conflicts):
        # Fetch the feature branch version of this file to compare content.
        try:
            show_rc, branch_content, _ = await run_git(
                ["show", f"{feature_branch}:{path}"],
                cwd=repo_root,
                check=False,
            )
        except Exception:
            # Encoding error (e.g. binary file) or other failure — cannot
            # verify content; preserve the file conservatively.
            logger.warning(
                "Cannot verify untracked file '%s' against feature branch '%s'; "
                "skipping deletion to preserve potential local work",
                path,
                feature_branch,
            )
            unverifiable.append(path)
            continue

        if show_rc != 0:
            # git show returned an error — skip conservatively.
            logger.warning(
                "Cannot verify untracked file '%s' against feature branch '%s' "
                "(git show returned %d); skipping deletion",
                path,
                feature_branch,
                show_rc,
            )
            unverifiable.append(path)
            continue

        # Compare on-disk content with the branch version.
        full = repo_root / path
        try:
            disk_content = full.read_text()
        except OSError:
            unverifiable.append(path)
            continue

        if disk_content == branch_content:
            safe_to_remove.append(path)
        else:
            divergent.append(path)

    if divergent:
        logger.warning(
            "Refusing to remove %d untracked file(s) whose content differs from feature branch '%s': %s",
            len(divergent),
            feature_branch,
            ", ".join(divergent),
        )
        raise IntegrationError(
            f"Untracked file(s) with content that diverges from the feature "
            f"branch would be overwritten by merge: {', '.join(divergent)}",
            branch=feature_branch,
        )

    if safe_to_remove:
        logger.warning(
            "Removing %d untracked file(s) that would block merge (content matches feature branch '%s'): %s",
            len(safe_to_remove),
            feature_branch,
            ", ".join(sorted(safe_to_remove)),
        )
        for path in safe_to_remove:
            full = repo_root / path
            try:
                full.unlink(missing_ok=True)
            except OSError:
                logger.debug("Could not remove untracked file %s", full)


async def _build_squash_message(
    repo_root: Path,
    feature_branch: str,
    dev_branch: str,
) -> str:
    """Build a clean commit message for a squash merge.

    Uses the tip commit's full message as the commit message.  For
    multi-commit branches, appends the earlier commit subjects as a
    bullet list so they are not lost.
    """
    _, tip_msg, _ = await run_git(
        ["log", "-1", "--format=%B", feature_branch],
        cwd=repo_root,
        check=False,
    )
    msg = tip_msg.strip() if tip_msg else ""
    if not msg:
        return f"Squash merge {feature_branch}"

    _, count_str, _ = await run_git(
        ["rev-list", "--count", f"{dev_branch}..{feature_branch}"],
        cwd=repo_root,
        check=False,
    )
    count = int(count_str.strip()) if count_str and count_str.strip().isdigit() else 1

    if count > 1:
        _, all_subjects, _ = await run_git(
            ["log", "--format=- %s", f"{dev_branch}..{feature_branch}"],
            cwd=repo_root,
            check=False,
        )
        if all_subjects:
            other_lines = all_subjects.strip().splitlines()[1:]
            if other_lines:
                msg += "\n\n" + "\n".join(other_lines)

    return msg


async def _harvest_under_lock(
    repo_root: Path,
    workspace: WorkspaceInfo,
    dev_branch: str,
) -> list[str]:
    """Execute the harvest squash-merge under the merge lock.

    Always uses ``git merge --squash`` to produce a single commit on
    dev_branch regardless of the feature branch topology.  On conflict,
    spawns the merge agent to resolve.

    Called from harvest() after the lock is acquired.

    Requirements: 45-REQ-4.1, 45-REQ-6.1
    """
    # Ensure a clean working tree before any merge operation. A prior
    # failed harvest may have left tracked files dirty, which would cause
    # subsequent checkout/merge commands to fail.
    await run_git(["checkout", "--", "."], cwd=repo_root, check=False)

    # Remove untracked files that would block the merge. A prior session
    # may have created files (e.g. test files) that now exist both as
    # untracked in the working tree and in the incoming feature branch.
    await _clean_conflicting_untracked(repo_root, workspace.branch)

    # Capture the list of changed files before switching branches
    changed_files = await get_changed_files(
        repo_root,
        workspace.branch,
        dev_branch,
    )

    # Checkout the development branch in the main repo
    await checkout_branch(repo_root, dev_branch)

    # Squash merge produces a single commit on dev_branch, collapsing
    # any internal merge topology on the feature branch.
    merge_rc, merge_stdout, merge_stderr = await run_git(
        ["merge", "--squash", "--", workspace.branch],
        cwd=repo_root,
        check=False,
    )
    if merge_rc != 0:
        # Spawn merge agent to resolve conflicts (45-REQ-4.1, 45-REQ-6.1)
        merge_detail = merge_stderr.strip() or merge_stdout.strip()
        logger.info(
            "Squash merge of '%s' had conflicts, spawning merge agent",
            workspace.branch,
        )
        resolved = await run_merge_agent(
            worktree_path=repo_root,
            conflict_output=merge_detail,
            model_id="ADVANCED",
        )
        if not resolved:
            # Abort the failed squash merge and raise.
            # Squash does not set MERGE_HEAD, so use reset --merge.
            await run_git(
                ["reset", "--merge"],
                cwd=repo_root,
                check=False,
            )
            raise IntegrationError(
                f"Merge agent failed to resolve conflicts for '{workspace.branch}' into '{dev_branch}'",
                branch=workspace.branch,
            )
    else:
        # Squash stages changes but does not commit. Commit them now,
        # unless the squash resulted in no changes (identical content
        # already on dev_branch).
        diff_rc, _, _ = await run_git(
            ["diff", "--cached", "--quiet"],
            cwd=repo_root,
            check=False,
        )
        if diff_rc != 0:
            msg = await _build_squash_message(
                repo_root,
                workspace.branch,
                dev_branch,
            )
            await run_git(["commit", "-m", msg], cwd=repo_root)

    logger.info(
        "Squash merge of '%s' into '%s' succeeded",
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
            "origin/develop is %d commit(s) ahead. Attempting reconciliation before push.",
            remote_ahead,
        )
        try:
            await _sync_develop_with_remote(repo_root)
        except Exception as e:
            # If reconciliation fails (e.g., fetch failed), skip and attempt
            # push as-is (36-REQ-2.E2)
            logger.debug(
                "Reconciliation failed: %s. Skipping reconciliation and attempting push as-is.",
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
) -> None:
    """Push develop to origin after harvest.

    Feature branches are kept local-only and are not pushed to the remote.
    The workspace parameter is retained for logging context.

    All remote operations are best-effort: failures are logged as warnings
    and never raised.

    Requirements: 65-REQ-3.2, 65-REQ-3.3, 65-REQ-3.4, 65-REQ-3.5,
                  65-REQ-3.E2, 78-REQ-1.1, 78-REQ-1.2, 78-REQ-1.3,
                  78-REQ-1.E1
    """
    # Push only develop — feature branches are local-only (78-REQ-1.1)
    await _push_develop_if_pushable(repo_root)
