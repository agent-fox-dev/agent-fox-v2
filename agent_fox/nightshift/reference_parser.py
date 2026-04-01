"""Reference parser: explicit dependency extraction from issue text and GitHub.

Requirements: 71-REQ-2.1, 71-REQ-2.2, 71-REQ-2.3, 71-REQ-2.E1
"""

from __future__ import annotations

from agent_fox.nightshift.dep_graph import DependencyEdge
from agent_fox.platform.github import IssueResult


def parse_text_references(issues: list[IssueResult]) -> list[DependencyEdge]:
    """Extract dependency edges from issue body text.

    Matches case-insensitive patterns: "depends on #N", "blocked by #N",
    "after #N", "requires #N". Only returns edges where both endpoints
    are in the batch.

    NOT YET IMPLEMENTED — stub for task group 1 tests.
    """
    raise NotImplementedError("parse_text_references not yet implemented")


async def fetch_github_relationships(
    platform: object,
    issues: list[IssueResult],
) -> list[DependencyEdge]:
    """Query GitHub for parent/blocks/is-blocked-by relationships.

    NOT YET IMPLEMENTED — stub for task group 1 tests.
    """
    raise NotImplementedError("fetch_github_relationships not yet implemented")
