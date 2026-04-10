"""Auditor output persistence, GitHub issue filing, and audit events.

Handles writing audit reports, filing/closing GitHub issues on auditor verdicts,
and creating audit event payloads for the retry loop.

Requirements: 46-REQ-8.1, 46-REQ-8.2, 46-REQ-8.3, 46-REQ-8.4,
              46-REQ-8.E1, 46-REQ-8.E2, 46-REQ-7.6,
              92-REQ-1.1, 92-REQ-1.2, 92-REQ-1.3, 92-REQ-1.E1,
              92-REQ-2.1, 92-REQ-3.1, 92-REQ-3.E1, 92-REQ-3.E2,
              92-REQ-4.2, 92-REQ-4.E1, 92-REQ-4.E2
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
# Output persistence (46-REQ-8.1, 46-REQ-8.E2, 92-REQ-1.1–1.3, 92-REQ-2.1,
#                    92-REQ-3.1, 92-REQ-3.E1, 92-REQ-3.E2)
# ---------------------------------------------------------------------------


def persist_auditor_results(
    spec_dir: Path,
    result: AuditResult,
    *,
    attempt: int = 1,
) -> None:
    """Write audit findings to .agent-fox/audit/audit_{spec_name}.md.

    For PASS verdicts, deletes any existing audit report and writes nothing.
    For non-PASS verdicts, creates the audit directory if needed and writes
    (or overwrites) the report.

    Handles filesystem errors gracefully — logs and does not raise.

    Requirements: 46-REQ-8.1, 46-REQ-8.E2,
                  92-REQ-1.1, 92-REQ-1.2, 92-REQ-1.3, 92-REQ-1.E1,
                  92-REQ-2.1, 92-REQ-3.1, 92-REQ-3.E1, 92-REQ-3.E2
    """
    spec_name = spec_dir.name
    audit_dir = spec_dir.parent.parent / ".agent-fox" / "audit"
    audit_path = audit_dir / f"audit_{spec_name}.md"

    # PASS verdict: delete existing report and return (do not write).
    # Requirements: 92-REQ-3.1, 92-REQ-3.E1, 92-REQ-3.E2
    if result.overall_verdict == "PASS":
        try:
            audit_path.unlink(missing_ok=True)
            logger.info("Removed audit report for %s (PASS verdict)", spec_name)
        except OSError:
            logger.error(
                "Failed to delete audit report for %s",
                spec_name,
                exc_info=True,
            )
        return

    # Non-PASS: ensure output directory exists before writing.
    # Requirements: 92-REQ-1.2, 92-REQ-1.E1
    try:
        audit_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.error(
            "Failed to create audit directory %s",
            audit_dir,
            exc_info=True,
        )
        return

    # Write (or overwrite) the audit report.
    # Requirements: 92-REQ-1.1, 92-REQ-1.3, 92-REQ-2.1
    try:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            f"# Audit Report: {spec_name}",
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

        lines.extend(
            [
                "",
                "## Summary",
                "",
                result.summary or "No summary provided.",
                "",
            ]
        )

        audit_path.write_text("\n".join(lines))
        logger.info("Wrote audit report to %s", audit_path)
    except OSError:
        logger.error("Failed to write audit report to %s", audit_path, exc_info=True)


# ---------------------------------------------------------------------------
# Completion cleanup (92-REQ-4.2, 92-REQ-4.E1, 92-REQ-4.E2)
# ---------------------------------------------------------------------------


def cleanup_completed_spec_audits(
    project_root: Path,
    completed_specs: set[str],
) -> None:
    """Delete audit report files for fully-completed specs.

    Iterates the given spec names and deletes each matching audit file
    from ``.agent-fox/audit/``.  Per-spec OSErrors are logged as warnings
    and do not stop processing of the remaining specs.

    Args:
        project_root: Root directory of the project (parent of
            ``.agent-fox/``).
        completed_specs: Set of spec folder names (e.g. ``"05_foo"``)
            whose audit reports should be removed.

    Requirements: 92-REQ-4.2, 92-REQ-4.E1, 92-REQ-4.E2
    """
    audit_dir = project_root / ".agent-fox" / "audit"
    for spec in completed_specs:
        audit_path = audit_dir / f"audit_{spec}.md"
        try:
            audit_path.unlink(missing_ok=True)
            logger.info("Removed audit report for completed spec %s", spec)
        except OSError:
            logger.warning(
                "Failed to delete audit report for completed spec %s",
                spec,
                exc_info=True,
            )


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
            "No GitHub platform available; skipping auditor issue management for %s",
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

    lines.extend(
        [
            "",
            "### Summary",
            "",
            result.summary or "No summary.",
        ]
    )

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
