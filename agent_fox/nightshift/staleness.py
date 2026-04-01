"""Staleness check: post-fix evaluation of remaining issues.

Requirements: 71-REQ-5.1, 71-REQ-5.2, 71-REQ-5.3, 71-REQ-5.4,
              71-REQ-5.E1, 71-REQ-5.E2, 71-REQ-5.E3
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_fox.platform.github import IssueResult


@dataclass(frozen=True)
class StalenessResult:
    """Result of post-fix staleness evaluation."""

    obsolete_issues: list[int]  # issue numbers to close
    rationale: dict[int, str] = field(default_factory=dict)  # issue_number -> why


async def _run_ai_staleness(
    fixed_issue: IssueResult,
    remaining_issues: list[IssueResult],
    fix_diff: str,
    config: object,
) -> StalenessResult:
    """Internal: run the actual AI staleness evaluation.

    NOT YET IMPLEMENTED — stub for task group 1 tests.
    """
    raise NotImplementedError("_run_ai_staleness not yet implemented")


async def check_staleness(
    fixed_issue: IssueResult,
    remaining_issues: list[IssueResult],
    fix_diff: str,
    config: object,
    platform: object,
) -> StalenessResult:
    """Evaluate remaining issues for obsolescence after a fix.

    Uses AI analysis + GitHub API verification.

    NOT YET IMPLEMENTED — stub for task group 1 tests.
    """
    raise NotImplementedError("check_staleness not yet implemented")
