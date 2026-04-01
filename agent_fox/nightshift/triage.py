"""AI batch triage: prompt construction, response parsing, order recommendation.

Requirements: 71-REQ-3.1, 71-REQ-3.2, 71-REQ-3.3, 71-REQ-3.E1, 71-REQ-3.E2
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_fox.nightshift.dep_graph import DependencyEdge
from agent_fox.platform.github import IssueResult


class TriageError(Exception):
    """Raised when AI triage fails."""


@dataclass(frozen=True)
class TriageResult:
    """Output of AI batch triage."""

    processing_order: list[int]  # recommended issue numbers in order
    edges: list[DependencyEdge]  # AI-detected dependencies
    supersession_pairs: list[tuple[int, int]]  # (keep, obsolete) pairs


async def _run_ai_triage(
    issues: list[IssueResult],
    explicit_edges: list[DependencyEdge],
    config: object,
) -> TriageResult:
    """Internal: run the actual AI triage call.

    NOT YET IMPLEMENTED — stub for task group 1 tests.
    """
    raise NotImplementedError("_run_ai_triage not yet implemented")


async def run_batch_triage(
    issues: list[IssueResult],
    explicit_edges: list[DependencyEdge],
    config: object,
) -> TriageResult:
    """Run ADVANCED-tier AI analysis on the fix batch.

    Raises TriageError on failure (caller falls back to explicit refs).

    NOT YET IMPLEMENTED — stub for task group 1 tests.
    """
    raise NotImplementedError("run_batch_triage not yet implemented")
