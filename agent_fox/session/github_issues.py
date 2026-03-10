"""GitHub issue search-before-create idempotency via REST API.

Provides ``file_or_update_issue()`` which searches for an existing open issue
with a matching title prefix before creating a new one. On re-runs, existing
issues are updated rather than duplicated.

All REST API failures are logged and swallowed -- GitHub issue filing never
blocks session completion.

Requirements: 28-REQ-5.1, 28-REQ-5.2, 28-REQ-5.3, 28-REQ-5.4,
              28-REQ-5.E1, 28-REQ-5.E2,
              27-REQ-7.1, 27-REQ-7.2, 27-REQ-7.E1
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_fox.platform.github import GitHubPlatform

logger = logging.getLogger(__name__)


async def file_or_update_issue(
    title_prefix: str,
    body: str,
    *,
    platform: GitHubPlatform | None = None,
    close_if_empty: bool = False,
) -> str | None:
    """Search-before-create GitHub issue idempotency.

    Uses the GitHubPlatform REST API instead of the gh CLI.

    1. If platform is None: log warning, return None.
    2. Search for existing open issue with matching title prefix.
    3. If found and close_if_empty and body is empty: close issue.
    4. If found: update body, add comment noting re-run.
    5. If not found: create new issue.

    Returns issue URL or None on failure.
    Failures are logged but never raise.

    Requirements: 28-REQ-5.1, 28-REQ-5.2, 28-REQ-5.3, 28-REQ-5.E1, 28-REQ-5.E2
    """
    if platform is None:
        logger.warning(
            "No GitHubPlatform provided; cannot file GitHub issue for '%s'",
            title_prefix,
        )
        return None

    try:
        # 1. Search for existing open issue
        results = await platform.search_issues(title_prefix)

        if results:
            existing = results[0]

            # Close if empty and close_if_empty is set
            if close_if_empty and not body.strip():
                await platform.close_issue(
                    existing.number,
                    comment="Closing: no findings on re-run.",
                )
                logger.info(
                    "Closed issue #%d (no findings): %s",
                    existing.number,
                    title_prefix,
                )
                return None

            # Update existing issue
            await platform.update_issue(existing.number, body)
            await platform.add_issue_comment(existing.number, "Updated on re-run.")
            logger.info(
                "Updated existing issue #%d: %s",
                existing.number,
                title_prefix,
            )
            return existing.html_url

        # 2. Create new issue
        result = await platform.create_issue(title_prefix, body)
        logger.info("Created new issue #%d: %s", result.number, result.html_url)
        return result.html_url

    except Exception:
        logger.warning(
            "GitHub issue filing failed for '%s'; continuing without issue",
            title_prefix,
            exc_info=True,
        )
        return None


def format_issue_body_from_findings(
    findings: list,
) -> str:
    """Format a GitHub issue body from ReviewFinding records.

    Groups findings by severity and renders as markdown. Returns empty
    string if no findings.

    Requirements: 27-REQ-7.1
    """
    if not findings:
        return ""

    severity_order = ["critical", "major", "minor", "observation"]
    grouped: dict[str, list] = {}
    for f in findings:
        grouped.setdefault(f.severity, []).append(f)

    lines = ["## Blocking Findings", ""]

    for sev in severity_order:
        sev_findings = grouped.get(sev, [])
        if not sev_findings:
            continue
        lines.append(f"### {sev.capitalize()}")
        for f in sev_findings:
            ref = f" (ref: {f.requirement_ref})" if f.requirement_ref else ""
            lines.append(f"- {f.description}{ref}")
        lines.append("")

    spec_name = findings[0].spec_name if findings else "unknown"
    lines.append(f"*Spec: {spec_name}*")

    return "\n".join(lines)
