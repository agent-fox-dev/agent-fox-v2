"""Auditor output persistence, GitHub issue filing, and audit events.

Handles writing audit.md, filing/closing GitHub issues on auditor verdicts,
and creating audit event payloads for the retry loop.

Requirements: 46-REQ-8.1, 46-REQ-8.2, 46-REQ-8.3, 46-REQ-8.4,
              46-REQ-8.E1, 46-REQ-8.E2, 46-REQ-7.6
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_fox.session.convergence import AuditResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output persistence (46-REQ-8.1, 46-REQ-8.E2)
# ---------------------------------------------------------------------------


def persist_auditor_results(
    spec_dir: Path,
    result: AuditResult,
    *,
    attempt: int = 1,
) -> None:
    """Write audit findings to spec_dir/audit.md.

    Handles filesystem errors gracefully — logs and does not raise.

    Requirements: 46-REQ-8.1, 46-REQ-8.E2
    """
    try:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            f"# Audit Report: {spec_dir.name}",
            "",
            f"**Overall Verdict:** {result.overall_verdict}",
            f"**Date:** {now}",
            f"**Attempt:** {attempt}",
            "",
            "## Per-Entry Results",
            "",
            "| TS Entry | Verdict | Test Functions | Notes |",
            "|----------|---------|----------------|-------|",
        ]

        for entry in result.entries:
            funcs = ", ".join(entry.test_functions) if entry.test_functions else "-"
            notes = entry.notes or "-"
            lines.append(f"| {entry.ts_entry} | {entry.verdict} | {funcs} | {notes} |")

        lines.extend([
            "",
            "## Summary",
            "",
            result.summary or "No summary provided.",
            "",
        ])

        audit_path = spec_dir / "audit.md"
        audit_path.write_text("\n".join(lines))
        logger.info("Wrote audit report to %s", audit_path)
    except OSError:
        logger.error("Failed to write audit.md to %s", spec_dir, exc_info=True)


# ---------------------------------------------------------------------------
# GitHub issue filing (46-REQ-8.2, 46-REQ-8.3, 46-REQ-8.E1, 46-REQ-7.6)
# ---------------------------------------------------------------------------


def create_circuit_breaker_issue_title(spec_name: str) -> str:
    """Create the GitHub issue title for a circuit breaker trip.

    Requirement: 46-REQ-7.6
    """
    return f"[Auditor] {spec_name}: circuit breaker tripped"


def _create_fail_issue_title(spec_name: str) -> str:
    """Create the GitHub issue title for a FAIL verdict.

    Requirement: 46-REQ-8.2
    """
    return f"[Auditor] {spec_name}: FAIL"


async def handle_auditor_github_issue(
    spec_name: str,
    result: AuditResult,
    *,
    platform: Any | None = None,
) -> None:
    """File or close GitHub issues based on auditor verdict.

    - FAIL: file issue with search-before-create pattern
    - PASS: close existing issue if found

    If platform is None or unavailable, logs warning and returns.

    Requirements: 46-REQ-8.2, 46-REQ-8.3, 46-REQ-8.E1
    """
    if platform is None:
        logger.warning(
            "No GitHub platform available; skipping auditor issue management "
            "for %s",
            spec_name,
        )
        return

    try:
        if result.overall_verdict == "FAIL":
            title = _create_fail_issue_title(spec_name)
            # Search before create
            prefix = f"[Auditor] {spec_name}"
            existing = await platform.search_issues(title_prefix=prefix)
            if not existing:
                body = _format_issue_body(spec_name, result)
                await platform.create_issue(title=title, body=body)
                logger.info("Filed auditor FAIL issue for %s", spec_name)
            else:
                logger.info(
                    "Auditor FAIL issue already exists for %s (#%d)",
                    spec_name,
                    existing[0].number,
                )
        elif result.overall_verdict == "PASS":
            # Close existing issue if found
            prefix = f"[Auditor] {spec_name}"
            existing = await platform.search_issues(title_prefix=prefix)
            if existing:
                await platform.close_issue(
                    issue_number=existing[0].number,
                    comment="Auditor verdict is now PASS. Closing.",
                )
                logger.info(
                    "Closed auditor issue #%d for %s",
                    existing[0].number,
                    spec_name,
                )
    except Exception:
        logger.warning(
            "Failed to manage GitHub issue for auditor verdict on %s",
            spec_name,
            exc_info=True,
        )


def _format_issue_body(spec_name: str, result: AuditResult) -> str:
    """Format the GitHub issue body for an auditor FAIL verdict."""
    lines = [
        f"## Auditor Report: {spec_name}",
        "",
        f"**Overall Verdict:** {result.overall_verdict}",
        "",
        "### Per-Entry Results",
        "",
        "| TS Entry | Verdict | Notes |",
        "|----------|---------|-------|",
    ]

    for entry in result.entries:
        notes = entry.notes or "-"
        lines.append(f"| {entry.ts_entry} | {entry.verdict} | {notes} |")

    lines.extend([
        "",
        "### Summary",
        "",
        result.summary or "No summary.",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Audit events (46-REQ-8.4)
# ---------------------------------------------------------------------------


def create_auditor_retry_event(
    spec_name: str,
    group_number: int | float,
    attempt: int,
) -> dict[str, Any]:
    """Create an auditor.retry audit event payload.

    Requirement: 46-REQ-8.4
    """
    return {
        "event_type": "auditor.retry",
        "spec_name": spec_name,
        "group_number": group_number,
        "attempt": attempt,
    }


def create_circuit_breaker_event(
    spec_name: str,
    group_number: int | float,
    max_retries: int,
    last_findings_summary: str,
) -> dict[str, Any]:
    """Create an auditor.circuit_breaker audit event payload.

    Requirement: 46-REQ-7.6
    """
    return {
        "event_type": "auditor.circuit_breaker",
        "spec_name": spec_name,
        "group_number": group_number,
        "max_retries": max_retries,
        "last_findings_summary": last_findings_summary,
    }
