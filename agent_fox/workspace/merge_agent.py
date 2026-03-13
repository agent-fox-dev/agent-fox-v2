"""Merge agent: resolve git conflicts via an AI coding session.

Spawns a dedicated coding agent to resolve merge conflicts when deterministic
strategies (fast-forward, rebase, merge commit) fail. The agent is restricted
to conflict resolution only -- no test fixes, refactoring, or feature changes.

Requirements: 45-REQ-4.1 through 45-REQ-4.5,
              45-REQ-4.E1, 45-REQ-4.E2
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MERGE_AGENT_SYSTEM_PROMPT = """\
You are a merge conflict resolution agent. Your ONLY task is to resolve \
git merge conflicts in the working tree.

Rules:
- Resolve merge conflicts only. Do NOT refactor code, fix test failures, \
or make feature changes.
- Open each conflicted file, understand both sides of the conflict, and \
produce a correct merged result.
- After resolving all conflicts, stage the resolved files with `git add` \
and commit with a merge commit message.
- Do not modify any files that are not part of the merge conflict.
- Do not run tests or make any changes beyond what is needed to resolve \
the conflicts.
"""


async def run_merge_agent(
    worktree_path: Path,
    conflict_output: str,
    model_id: str,
) -> bool:
    """Spawn a merge agent to resolve git conflicts.

    Args:
        worktree_path: Path to the git worktree with unresolved conflicts.
        conflict_output: Git conflict/diff output to include in the prompt.
        model_id: Model ID to use (resolved from ADVANCED tier).

    Returns:
        True if conflicts were resolved and committed, False otherwise.

    Requirements: 45-REQ-4.1, 45-REQ-4.2, 45-REQ-4.3, 45-REQ-4.4,
                  45-REQ-4.5, 45-REQ-4.E1, 45-REQ-4.E2
    """
    task_prompt = (
        "Resolve the following git merge conflicts in the working tree.\n\n"
        "Git conflict output:\n"
        f"```\n{conflict_output}\n```\n\n"
        "Resolve all conflicts, stage the files, and commit."
    )

    try:
        session_ok = await _run_agent_session(
            worktree_path=worktree_path,
            system_prompt=MERGE_AGENT_SYSTEM_PROMPT,
            task_prompt=task_prompt,
            model_id=model_id,
        )
    except Exception:
        logger.exception(
            "Merge agent session failed with exception (worktree=%s)",
            worktree_path,
        )
        return False

    if not session_ok:
        logger.error(
            "Merge agent session returned failure (worktree=%s)",
            worktree_path,
        )
        return False

    # Verify conflicts are actually resolved
    resolved = await _check_conflicts_resolved(worktree_path)
    if not resolved:
        logger.error(
            "Merge agent did not resolve all conflicts (worktree=%s)",
            worktree_path,
        )
        return False

    logger.info("Merge agent resolved all conflicts (worktree=%s)", worktree_path)
    return True


async def _run_agent_session(
    worktree_path: Path,
    system_prompt: str,
    task_prompt: str,
    model_id: str,
) -> bool:
    """Run a coding agent session for conflict resolution.

    This is the internal integration point with the session runner.
    Separated for testability -- tests mock this function to avoid
    spawning real agent sessions.

    Returns:
        True if the session completed successfully, False otherwise.
    """
    from agent_fox.core.config import load_config
    from agent_fox.session.session import run_session
    from agent_fox.workspace.workspace import WorkspaceInfo

    config = load_config()

    workspace = WorkspaceInfo(
        path=worktree_path,
        branch="merge-resolution",
        spec_name="merge-agent",
        task_group=0,
    )

    try:
        outcome = await run_session(
            workspace=workspace,
            node_id="merge-agent",
            system_prompt=system_prompt,
            task_prompt=task_prompt,
            config=config,
            model_id=model_id,
        )
        return outcome.status == "completed"
    except Exception:
        logger.exception("Agent session raised an exception")
        return False


async def _check_conflicts_resolved(worktree_path: Path) -> bool:
    """Check if all merge conflicts have been resolved.

    Uses ``git diff --check`` to detect remaining conflict markers.

    Returns:
        True if no conflict markers remain, False otherwise.
    """
    from agent_fox.workspace.workspace import run_git

    rc, _stdout, _stderr = await run_git(
        ["diff", "--check"],
        cwd=worktree_path,
        check=False,
    )
    return rc == 0
