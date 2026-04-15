"""Reference parser: explicit dependency extraction from issue text and GitHub.

Requirements: 71-REQ-2.1, 71-REQ-2.2, 71-REQ-2.3, 71-REQ-2.E1
"""

from __future__ import annotations

import logging
import re

from agent_fox.nightshift.dep_graph import DependencyEdge
from agent_fox.platform.protocol import IssueResult

logger = logging.getLogger(__name__)

# Case-insensitive patterns: "depends on #N", "blocked by #N",
# "after #N", "requires #N".
_DEPENDENCY_PATTERN = re.compile(
    r"(?:depends\s+on|blocked\s+by|after|requires)\s+#(\d+)",
    re.IGNORECASE,
)


def parse_text_references(issues: list[IssueResult]) -> list[DependencyEdge]:
    """Extract dependency edges from issue body text.

    Matches case-insensitive patterns: "depends on #N", "blocked by #N",
    "after #N", "requires #N". Only returns edges where both endpoints
    are in the batch.

    Requirements: 71-REQ-2.1, 71-REQ-2.3, 71-REQ-2.E1
    """
    batch_numbers = {i.number for i in issues}
    edges: list[DependencyEdge] = []

    for issue in issues:
        if not issue.body:
            continue
        for match in _DEPENDENCY_PATTERN.finditer(issue.body):
            ref_number = int(match.group(1))
            # Only include edges where both endpoints are in the batch
            # (71-REQ-2.E1)
            if ref_number in batch_numbers and ref_number != issue.number:
                edges.append(
                    DependencyEdge(
                        from_issue=ref_number,
                        to_issue=issue.number,
                        source="explicit",
                        rationale=f"Issue #{issue.number} body: '{match.group(0)}'",
                    )
                )

    return edges


async def fetch_github_relationships(
    platform: object,
    issues: list[IssueResult],
) -> list[DependencyEdge]:
    """Query GitHub for parent/blocks/is-blocked-by relationships.

    Uses the timeline API to find cross-referenced events between issues
    in the batch. Handles 404/403 gracefully by returning an empty list.

    Requirements: 71-REQ-2.2
    """
    batch_numbers = {i.number for i in issues}
    edges: list[DependencyEdge] = []

    get_timeline = getattr(platform, "get_issue_timeline", None)
    if get_timeline is None:
        logger.debug("Platform does not support get_issue_timeline, skipping")
        return edges

    for issue in issues:
        try:
            events = await get_timeline(issue.number)
        except Exception:
            logger.debug(
                "Failed to fetch timeline for issue #%d",
                issue.number,
                exc_info=True,
            )
            continue

        for event in events:
            event_type = event.get("event", "")
            if event_type == "cross-referenced":
                source_issue = event.get("source", {}).get("issue", {}).get("number")
                if source_issue is not None and source_issue in batch_numbers and source_issue != issue.number:
                    edges.append(
                        DependencyEdge(
                            from_issue=source_issue,
                            to_issue=issue.number,
                            source="github",
                            rationale=(f"GitHub cross-reference: #{source_issue} referenced in #{issue.number}"),
                        )
                    )

    return edges
