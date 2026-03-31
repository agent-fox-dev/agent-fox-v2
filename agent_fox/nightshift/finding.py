"""Finding dataclass, FindingGroup, consolidation, and issue body generation.

Requirements: 61-REQ-3.3, 61-REQ-5.1, 61-REQ-5.2, 61-REQ-5.3, 61-REQ-5.E1
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Finding:
    """Standardised output from a hunt category.

    Requirements: 61-REQ-3.3
    """

    category: str
    title: str
    description: str
    severity: str  # "critical" | "major" | "minor" | "info"
    affected_files: list[str]
    suggested_fix: str
    evidence: str
    group_key: str


@dataclass(frozen=True)
class FindingGroup:
    """A group of related findings for a single issue.

    Requirements: 61-REQ-5.1
    """

    findings: list[Finding]
    title: str
    body: str
    category: str


def consolidate_findings(findings: list[Finding]) -> list[FindingGroup]:
    """Group findings by root cause (group_key).

    Each unique group_key produces one FindingGroup. The group title
    is derived from the first finding in the group, and the category
    is taken from the first finding.

    Requirements: 61-REQ-5.1
    """
    groups_map: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        groups_map[finding.group_key].append(finding)

    groups: list[FindingGroup] = []
    for group_key, group_findings in groups_map.items():
        first = group_findings[0]
        group = FindingGroup(
            findings=group_findings,
            title=first.title,
            body=(
                f"{first.description}\n\n"
                f"Affected files: {', '.join(first.affected_files)}"
            ),
            category=first.category,
        )
        groups.append(group)

    return groups


def build_issue_body(group: FindingGroup) -> str:
    """Build a markdown issue body from a FindingGroup.

    Includes category, severity, affected files, and suggested fix.

    Requirements: 61-REQ-5.3
    """
    lines: list[str] = []
    lines.append(f"## {group.title}")
    lines.append("")
    lines.append(f"**Category:** {group.category}")
    lines.append("")

    # Collect all unique severities, files, and suggested fixes
    severities = sorted({f.severity for f in group.findings})
    all_files = sorted({fp for f in group.findings for fp in f.affected_files})
    suggested_fixes = [f.suggested_fix for f in group.findings if f.suggested_fix]

    lines.append(f"**Severity:** {', '.join(severities)}")
    lines.append("")

    if all_files:
        lines.append("### Affected Files")
        lines.append("")
        for fp in all_files:
            lines.append(f"- `{fp}`")
        lines.append("")

    lines.append("### Description")
    lines.append("")
    for finding in group.findings:
        lines.append(f"- **{finding.title}**: {finding.description}")
    lines.append("")

    if suggested_fixes:
        lines.append("### Suggested Remediation")
        lines.append("")
        for fix in suggested_fixes:
            lines.append(f"- {fix}")
        lines.append("")

    return "\n".join(lines)


async def create_issues_from_groups(
    groups: list[FindingGroup],
    platform: object,
) -> None:
    """Create one platform issue per FindingGroup.

    Continues on individual failures, logging errors.

    Requirements: 61-REQ-5.2, 61-REQ-5.E1
    """
    for group in groups:
        try:
            body = build_issue_body(group)
            await platform.create_issue(group.title, body)  # type: ignore[union-attr]
        except Exception:
            logger.warning(
                "Failed to create issue for group '%s': %s",
                group.title,
                "fail",
                exc_info=True,
            )
