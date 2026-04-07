"""Query and format review findings from DuckDB.

Provides query functions for review_findings, verification_results,
and drift_findings tables, plus formatting utilities for table and
JSON output.

Requirements: 84-REQ-4.1 through 84-REQ-4.6, 84-REQ-5.1, 84-REQ-5.2
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Severity ordering: lower number = higher severity
SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "major": 1,
    "minor": 2,
    "observation": 3,
}


@dataclass(frozen=True)
class FindingRow:
    """Unified row for displaying findings from any review table."""

    id: str
    severity: str
    archetype: str  # "skeptic", "verifier", "oracle"
    spec_name: str
    task_group: str
    description: str
    created_at: datetime


@dataclass(frozen=True)
class FindingsSummary:
    """Per-spec summary of active findings by severity."""

    spec_name: str
    critical: int
    major: int
    minor: int
    observation: int


def query_findings(
    conn: Any,
    *,
    spec: str | None = None,
    severity: str | None = None,
    archetype: str | None = None,
    run_id: str | None = None,
    active_only: bool = True,
) -> list[FindingRow]:
    """Query findings from DuckDB with optional filters.

    Queries review_findings (skeptic), verification_results (verifier),
    and drift_findings (oracle) tables, unifying results into FindingRow
    objects with an archetype discriminator.

    Args:
        conn: DuckDB connection.
        spec: Filter by spec_name.
        severity: Minimum severity level (critical > major > minor > observation).
        archetype: Filter to "skeptic", "verifier", or "oracle" table.
        run_id: Filter by run ID (returns empty list if run metadata unavailable).
        active_only: Only return non-superseded findings.

    Returns:
        List of FindingRow objects matching the filters.

    Requirements: 84-REQ-4.1, 84-REQ-4.2, 84-REQ-4.3, 84-REQ-4.4,
                  84-REQ-4.5, 84-REQ-4.6
    """
    if conn is None:
        return []

    # run_id filtering requires a join to audit_events or session metadata
    # which is not available in the review tables. Return empty list.
    if run_id is not None:
        return []

    # Determine which archetypes to include
    include_skeptic = archetype is None or archetype == "skeptic"
    include_verifier = archetype is None or archetype == "verifier"
    include_oracle = archetype is None or archetype == "oracle"

    severity_threshold: int | None = SEVERITY_ORDER.get(severity) if severity else None

    rows: list[FindingRow] = []

    if include_skeptic:
        rows.extend(_query_review_findings(conn, spec, severity_threshold, active_only))

    if include_verifier:
        rows.extend(_query_verification_results(conn, spec, severity_threshold, active_only))

    if include_oracle:
        rows.extend(_query_drift_findings(conn, spec, severity_threshold, active_only))

    # Sort by created_at descending (most recent first)
    rows.sort(key=lambda r: r.created_at, reverse=True)
    return rows


def _build_where(conditions: list[str]) -> str:
    """Build a SQL WHERE clause from a list of conditions."""
    return "WHERE " + " AND ".join(conditions) if conditions else ""


def _query_review_findings(
    conn: Any,
    spec: str | None,
    severity_threshold: int | None,
    active_only: bool,
) -> list[FindingRow]:
    """Query the review_findings table (skeptic archetype)."""
    conditions: list[str] = []
    params: list[Any] = []

    if active_only:
        conditions.append("superseded_by IS NULL")
    if spec:
        conditions.append("spec_name = ?")
        params.append(spec)

    where = _build_where(conditions)
    sql = (
        f"SELECT id, severity, spec_name, task_group, description, created_at "
        f"FROM review_findings {where} ORDER BY created_at DESC"
    )

    try:
        result = conn.execute(sql, params).fetchall()
    except Exception:
        logger.warning("Failed to query review_findings", exc_info=True)
        return []

    rows = []
    for row_id, sev, spec_name, task_group, desc, created_at in result:
        if severity_threshold is not None:
            row_sev_order = SEVERITY_ORDER.get(sev, 999)
            if row_sev_order > severity_threshold:
                continue
        rows.append(
            FindingRow(
                id=str(row_id),
                severity=sev,
                archetype="skeptic",
                spec_name=spec_name,
                task_group=task_group,
                description=desc,
                created_at=created_at,
            )
        )
    return rows


def _query_verification_results(
    conn: Any,
    spec: str | None,
    severity_threshold: int | None,
    active_only: bool,
) -> list[FindingRow]:
    """Query the verification_results table (verifier archetype).

    Maps VerificationResult to FindingRow:
    - severity: "major" for FAIL, "minor" for PASS
    - description: "<requirement_id>: <verdict>"
    """
    conditions: list[str] = []
    params: list[Any] = []

    if active_only:
        conditions.append("superseded_by IS NULL")
    if spec:
        conditions.append("spec_name = ?")
        params.append(spec)

    where = _build_where(conditions)
    sql = (
        f"SELECT id, requirement_id, verdict, evidence, spec_name, task_group, created_at "
        f"FROM verification_results {where} ORDER BY created_at DESC"
    )

    try:
        result = conn.execute(sql, params).fetchall()
    except Exception:
        logger.warning("Failed to query verification_results", exc_info=True)
        return []

    rows = []
    for row_id, req_id, verdict, evidence, spec_name, task_group, created_at in result:
        # Map verdict to severity for unified display
        severity = "major" if verdict == "FAIL" else "minor"
        if severity_threshold is not None:
            row_sev_order = SEVERITY_ORDER.get(severity, 999)
            if row_sev_order > severity_threshold:
                continue
        description = f"{req_id}: {verdict}"
        if evidence:
            description = f"{description} — {evidence}"
        rows.append(
            FindingRow(
                id=str(row_id),
                severity=severity,
                archetype="verifier",
                spec_name=spec_name,
                task_group=task_group,
                description=description,
                created_at=created_at,
            )
        )
    return rows


def _query_drift_findings(
    conn: Any,
    spec: str | None,
    severity_threshold: int | None,
    active_only: bool,
) -> list[FindingRow]:
    """Query the drift_findings table (oracle archetype)."""
    conditions: list[str] = []
    params: list[Any] = []

    if active_only:
        conditions.append("superseded_by IS NULL")
    if spec:
        conditions.append("spec_name = ?")
        params.append(spec)

    where = _build_where(conditions)
    sql = (
        f"SELECT id, severity, spec_name, task_group, description, created_at "
        f"FROM drift_findings {where} ORDER BY created_at DESC"
    )

    try:
        result = conn.execute(sql, params).fetchall()
    except Exception:
        logger.warning("Failed to query drift_findings", exc_info=True)
        return []

    rows = []
    for row_id, sev, spec_name, task_group, desc, created_at in result:
        if severity_threshold is not None:
            row_sev_order = SEVERITY_ORDER.get(sev, 999)
            if row_sev_order > severity_threshold:
                continue
        rows.append(
            FindingRow(
                id=str(row_id),
                severity=sev,
                archetype="oracle",
                spec_name=spec_name,
                task_group=task_group,
                description=desc,
                created_at=created_at,
            )
        )
    return rows


def query_findings_summary(
    conn: Any,
) -> list[FindingsSummary]:
    """Query per-spec summary of active critical/major findings.

    Returns a list of FindingsSummary objects, one per spec that has at
    least one active critical or major finding. Specs with only minor or
    observation findings are omitted.

    Args:
        conn: DuckDB connection, or None (returns empty list).

    Returns:
        Sorted list of FindingsSummary objects.

    Requirements: 84-REQ-5.1, 84-REQ-5.2, 84-REQ-5.E1
    """
    if conn is None:
        return []

    try:
        # Aggregate from review_findings (skeptic)
        review_rows = conn.execute(
            """
            SELECT spec_name, severity, COUNT(*) AS cnt
            FROM review_findings
            WHERE superseded_by IS NULL
            GROUP BY spec_name, severity
            """
        ).fetchall()

        # Aggregate from drift_findings (oracle)
        drift_rows = conn.execute(
            """
            SELECT spec_name, severity, COUNT(*) AS cnt
            FROM drift_findings
            WHERE superseded_by IS NULL
            GROUP BY spec_name, severity
            """
        ).fetchall()
    except Exception:
        logger.debug("Failed to query findings summary from DB", exc_info=True)
        return []

    # Accumulate counts per spec
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for spec_name, severity, cnt in review_rows:
        counts[spec_name][severity] += cnt
    for spec_name, severity, cnt in drift_rows:
        counts[spec_name][severity] += cnt

    # Only include specs that have at least one critical or major finding
    summary: list[FindingsSummary] = []
    for spec_name in sorted(counts):
        sev_counts = counts[spec_name]
        critical = sev_counts.get("critical", 0)
        major = sev_counts.get("major", 0)
        if critical > 0 or major > 0:
            summary.append(
                FindingsSummary(
                    spec_name=spec_name,
                    critical=critical,
                    major=major,
                    minor=sev_counts.get("minor", 0),
                    observation=sev_counts.get("observation", 0),
                )
            )

    return summary


def format_findings_table(
    findings: list[FindingRow],
    json_output: bool = False,
) -> str:
    """Format findings as a table or JSON array.

    Args:
        findings: List of FindingRow objects to format.
        json_output: If True, output as a JSON array instead of a text table.

    Returns:
        Formatted string (table or JSON).

    Requirements: 84-REQ-4.1, 84-REQ-4.6
    """
    if json_output:
        return json.dumps(
            [
                {
                    "id": f.id,
                    "severity": f.severity,
                    "archetype": f.archetype,
                    "spec_name": f.spec_name,
                    "task_group": f.task_group,
                    "description": f.description,
                    "created_at": (f.created_at.isoformat() if f.created_at else None),
                }
                for f in findings
            ],
            indent=2,
        )

    # Text table format
    col_widths = {
        "severity": 12,
        "archetype": 10,
        "spec": 25,
        "description": 80,
    }

    header = (
        f"{'SEVERITY':<{col_widths['severity']}} "
        f"{'ARCHETYPE':<{col_widths['archetype']}} "
        f"{'SPEC':<{col_widths['spec']}} "
        f"{'DESCRIPTION':<{col_widths['description']}} "
        f"CREATED"
    )
    separator = "-" * (
        col_widths["severity"] + col_widths["archetype"] + col_widths["spec"] + col_widths["description"] + 30
    )

    lines = [header, separator]
    for f in findings:
        desc = f.description[: col_widths["description"]]
        created = f.created_at.strftime("%Y-%m-%d %H:%M") if f.created_at else "N/A"
        line = (
            f"{f.severity:<{col_widths['severity']}} "
            f"{f.archetype:<{col_widths['archetype']}} "
            f"{f.spec_name:<{col_widths['spec']}} "
            f"{desc:<{col_widths['description']}} "
            f"{created}"
        )
        lines.append(line)

    return "\n".join(lines)
