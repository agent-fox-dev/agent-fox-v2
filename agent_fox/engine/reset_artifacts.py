"""Reset artifact helpers: worktree/branch cleanup, git rollback, spec sync.

Low-level functions that manipulate external artifacts (worktrees, branches,
tasks.md checkboxes, plan.json statuses) on behalf of the reset operations
in ``reset.py``.

Requirements: 07-REQ-4.1, 07-REQ-4.2, 35-REQ-3.1 .. 35-REQ-4.5
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

from agent_fox.core.errors import AgentFoxError
from agent_fox.core.node_id import parse_node_id
from agent_fox.engine.state import SessionRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worktree / branch cleanup
# ---------------------------------------------------------------------------


def _task_id_to_worktree_path(worktrees_dir: Path, task_id: str) -> Path:
    """Convert a task ID to its worktree directory path.

    Task ID format: "spec_name:group_number"
    Worktree path: worktrees_dir / spec_name / group_number
    """
    parsed = parse_node_id(task_id)
    if parsed.group_number:
        return worktrees_dir / parsed.spec_name / str(parsed.group_number)
    return worktrees_dir / task_id


def _task_id_to_branch_name(task_id: str) -> str:
    """Convert a task ID to its feature branch name.

    Task ID format: "spec_name:group_number"
    Branch name: "feature/spec_name/group_number"

    Must match the format used by ``workspace.py:create_worktree``.
    """
    parsed = parse_node_id(task_id)
    if parsed.group_number:
        return f"feature/{parsed.spec_name}/{parsed.group_number}"
    return f"feature/{task_id}"


def _clean_worktree(worktrees_dir: Path, task_id: str) -> str | None:
    """Remove a task's worktree directory if it exists.

    Args:
        worktrees_dir: Path to .agent-fox/worktrees/.
        task_id: The task identifier.

    Returns:
        The worktree path that was removed, or None if it didn't exist.
    """
    wt_path = _task_id_to_worktree_path(worktrees_dir, task_id)
    if wt_path.exists():
        try:
            shutil.rmtree(wt_path)
            logger.info("Removed worktree: %s", wt_path)
            return str(wt_path)
        except OSError as exc:
            logger.warning("Failed to remove worktree %s: %s", wt_path, exc)
    return None


def _clean_branch(repo_path: Path, task_id: str) -> str | None:
    """Delete a task's feature branch if it exists.

    The branch name is derived from the task ID:
    feature/{spec_name}-{group_number}.

    Args:
        repo_path: Path to the git repository root.
        task_id: The task identifier.

    Returns:
        The branch name that was deleted, or None if it didn't exist.
    """
    branch_name = _task_id_to_branch_name(task_id)
    try:
        result = subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info("Deleted branch: %s", branch_name)
            return branch_name
        # Branch doesn't exist or other non-fatal issue
        if "not found" in result.stderr.lower():
            return None
        logger.warning(
            "Failed to delete branch %s: %s",
            branch_name,
            result.stderr.strip(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Git branch delete failed for %s: %s", branch_name, exc)
    return None


def _prune_worktrees(repo_path: Path) -> None:
    """Run ``git worktree prune`` to remove stale worktree tracking entries.

    After a worktree directory is deleted with shutil.rmtree, git's internal
    tracking (under ``.git/worktrees/``) still references it.  Without pruning,
    ``git branch -D`` will refuse to delete the associated branch because git
    believes the worktree is still active.
    """
    try:
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("git worktree prune failed: %s", exc)


def _cleanup_task(
    task_id: str,
    worktrees_dir: Path,
    repo_path: Path,
) -> tuple[str | None, str | None]:
    """Clean up worktree and branch for a single task.

    Args:
        task_id: The task identifier.
        worktrees_dir: Path to .agent-fox/worktrees/.
        repo_path: Path to the git repository root.

    Returns:
        Tuple of (cleaned_worktree, cleaned_branch) where each is
        the path/name if cleaned, or None.
    """
    wt = _clean_worktree(worktrees_dir, task_id)
    if wt:
        _prune_worktrees(repo_path)
    br = _clean_branch(repo_path, task_id)
    return wt, br


def collect_cleanup(
    task_id: str,
    worktrees_dir: Path,
    repo_path: Path,
    cleaned_worktrees: list[str],
    cleaned_branches: list[str],
) -> None:
    """Clean up artifacts for a task and append results to the lists."""
    wt, br = _cleanup_task(task_id, worktrees_dir, repo_path)
    if wt:
        cleaned_worktrees.append(wt)
    if br:
        cleaned_branches.append(br)


# ---------------------------------------------------------------------------
# Git rollback helpers
# ---------------------------------------------------------------------------


def find_rollback_target(
    session_history: list[SessionRecord],
    repo_path: Path,
    target_commit_sha: str | None = None,
) -> str | None:
    """Determine the rollback commit SHA.

    For full reset (target_commit_sha=None): finds the earliest
    commit_sha in session_history and returns its first-parent
    predecessor on develop.

    For partial reset (target_commit_sha given): returns the
    first-parent predecessor of target_commit_sha on develop.

    Returns None if no valid rollback target can be determined.
    """
    if target_commit_sha is not None:
        sha = target_commit_sha
    else:
        # Find earliest non-empty commit_sha in session history
        shas = [r.commit_sha for r in session_history if r.commit_sha and r.status == "completed"]
        if not shas:
            return None
        sha = shas[0]  # First in history order = earliest

    # Get the first-parent predecessor
    try:
        result = subprocess.run(
            ["git", "rev-parse", f"{sha}~1"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "Cannot resolve rollback target for %s: %s",
                sha,
                result.stderr.strip(),
            )
            return None
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Git rev-parse failed for %s: %s", sha, exc)
        return None


def rollback_develop(
    repo_path: Path,
    target_sha: str,
) -> None:
    """Reset the develop branch to the given commit SHA.

    Checks out develop and runs git reset --hard <target_sha>.

    Raises:
        AgentFoxError: If the SHA cannot be resolved.
    """
    try:
        # Checkout develop
        checkout_result = subprocess.run(
            ["git", "checkout", "develop"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if checkout_result.returncode != 0:
            raise AgentFoxError(f"Failed to checkout develop: {checkout_result.stderr.strip()}")

        # Reset to target SHA
        reset_result = subprocess.run(
            ["git", "reset", "--hard", target_sha],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if reset_result.returncode != 0:
            raise AgentFoxError(f"Failed to reset develop to {target_sha}: {reset_result.stderr.strip()}")
        logger.info("Rolled back develop to %s", target_sha)
    except (OSError, subprocess.SubprocessError) as exc:
        raise AgentFoxError(f"Git rollback failed: {exc}") from exc


def find_affected_tasks(
    session_history: list[SessionRecord],
    new_head: str,
    repo_path: Path,
) -> list[str]:
    """Find task IDs whose commit_sha is not an ancestor of new_head.

    Uses ``git merge-base --is-ancestor`` to check each completed
    task's commit_sha against the new develop HEAD.
    """
    affected: list[str] = []
    for record in session_history:
        if not record.commit_sha or record.status != "completed":
            continue
        try:
            result = subprocess.run(
                [
                    "git",
                    "merge-base",
                    "--is-ancestor",
                    record.commit_sha,
                    new_head,
                ],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                # Not an ancestor => affected by rollback
                affected.append(record.node_id)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning(
                "merge-base check failed for %s: %s",
                record.node_id,
                exc,
            )
            affected.append(record.node_id)
    return affected


# ---------------------------------------------------------------------------
# Spec file synchronization (tasks.md checkboxes, plan.json statuses)
# ---------------------------------------------------------------------------

# Pattern matching a top-level task group line: "- [...] N."
_TOP_LEVEL_RE = re.compile(r"^- \[.\] \d+\.", re.MULTILINE)

# Pattern matching any checkbox with [x] or [-] (at any indent level)
_CHECKBOX_RE = re.compile(r"^(\s*- \[)[x\-](\] )", re.MULTILINE)


def reset_tasks_md_checkboxes(
    affected_task_ids: list[str],
    specs_dir: Path,
) -> None:
    """Reset tasks.md checkboxes for affected task groups to ``[ ]``.

    For each affected task ID (format: spec_name:group_number),
    finds the corresponding tasks.md, locates the top-level
    checkbox for that group number, and replaces ``[x]`` or ``[-]``
    with ``[ ]``. Skips missing files silently.
    """
    # Group task IDs by spec name
    spec_groups: dict[str, list[int]] = {}
    for task_id in affected_task_ids:
        parsed = parse_node_id(task_id)
        if not parsed.group_number:
            continue
        spec_groups.setdefault(parsed.spec_name, []).append(parsed.group_number)

    for spec_name, group_nums in spec_groups.items():
        tasks_md = specs_dir / spec_name / "tasks.md"
        if not tasks_md.exists():
            logger.info("Skipping missing tasks.md for spec %s", spec_name)
            continue

        text = tasks_md.read_text()
        for group_num in group_nums:
            text = _reset_group_checkboxes(text, group_num)

        tasks_md.write_text(text)


def _reset_group_checkboxes(text: str, group_num: int) -> str:
    """Reset all checkboxes within a task group section to ``[ ]``.

    Identifies the section belonging to *group_num* (from its top-level
    ``- [...] N.`` line to the next top-level line or EOF) and resets
    every ``[x]`` or ``[-]`` checkbox within that section.
    """
    # Find the top-level line for this group
    group_start_re = re.compile(rf"^- \[[x\- ]\] {group_num}\.", re.MULTILINE)
    match = group_start_re.search(text)
    if not match:
        return text

    section_start = match.start()

    # Find the next top-level group line after this one
    next_match = _TOP_LEVEL_RE.search(text, match.end())
    section_end = next_match.start() if next_match else len(text)

    # Extract the section, reset all [x]/[-] checkboxes, reassemble
    before = text[:section_start]
    section = text[section_start:section_end]
    after = text[section_end:]

    section = _CHECKBOX_RE.sub(r"\1 \2", section)

    return before + section + after


def reset_plan_statuses(
    plan_path: Path,
    affected_task_ids: list[str],
) -> None:
    """Set node statuses in plan.json to ``pending`` for affected tasks.

    Reads plan.json, updates each affected node's status field,
    and writes it back. Skips if plan.json does not exist.
    """
    if not plan_path.exists():
        logger.info("Skipping plan status update: %s not found", plan_path)
        return

    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read plan.json: %s", exc)
        return

    nodes = data.get("nodes", {})
    for task_id in affected_task_ids:
        if task_id in nodes:
            nodes[task_id]["status"] = "pending"

    plan_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
