"""Backing module for the ``fix`` CLI command.

Provides ``run_fix()`` as a callable entry point for the fix loop,
usable without the Click framework.

Requirements: 59-REQ-5.1, 59-REQ-5.2, 59-REQ-5.3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from agent_fox.fix.fix import run_fix_loop

if TYPE_CHECKING:
    from agent_fox.core.config import AgentFoxConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FixResult:
    """Structured result from a fix run."""

    passes_completed: int
    clusters_resolved: int
    clusters_remaining: int
    sessions_consumed: int
    termination_reason: str
    total_cost: float = 0.0


async def run_fix(
    config: AgentFoxConfig,
    issue_url: str | None = None,
    *,
    max_attempts: int = 3,
    auto_pr: bool = False,
    dry_run: bool = False,
    auto: bool = False,
    improve_passes: int = 3,
) -> FixResult:
    """Run the fix loop for quality check failures.

    This function can be called without the Click framework.

    Args:
        config: Loaded AgentFoxConfig.
        issue_url: Optional GitHub issue URL for context.
        max_attempts: Maximum number of fix passes.
        auto_pr: Whether to automatically create a PR (reserved).
        dry_run: Generate fix specs only, do not run sessions.
        auto: After repair, run iterative improvement passes.
        improve_passes: Maximum improvement passes (requires auto=True).

    Returns:
        FixResult with pass counts, cluster info, and termination reason.

    Requirements: 59-REQ-5.1, 59-REQ-5.2, 59-REQ-5.3
    """
    from agent_fox.fix.fix import FixSessionRunner

    project_root = Path.cwd()

    # Build session runner (None in dry-run mode)
    runner: FixSessionRunner | None = None
    if not dry_run:
        from agent_fox.cli.fix import _build_fix_session_runner

        runner = _build_fix_session_runner(config, project_root)

    result = await run_fix_loop(
        project_root=project_root,
        config=config,
        max_passes=max_attempts,
        session_runner=runner,
    )

    return FixResult(
        passes_completed=result.passes_completed,
        clusters_resolved=result.clusters_resolved,
        clusters_remaining=result.clusters_remaining,
        sessions_consumed=result.sessions_consumed,
        termination_reason=str(result.termination_reason),
        total_cost=getattr(result, "total_cost", 0.0),
    )
