"""CRUD operations for review_findings and verification_results tables.

Provides insert-with-supersession, active-record queries, and
session-scoped queries for convergence.

Requirements: 27-REQ-1.1, 27-REQ-2.1, 27-REQ-4.1, 27-REQ-4.2, 27-REQ-4.3,
              27-REQ-4.E1, 27-REQ-5.1, 27-REQ-5.2, 27-REQ-6.1, 27-REQ-6.2
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

import duckdb  # noqa: F401

logger = logging.getLogger(__name__)

VALID_SEVERITIES = {"critical", "major", "minor", "observation"}
VALID_VERDICTS = {"PASS", "FAIL"}

_SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2, "observation": 3}


@dataclass(frozen=True)
class ReviewFinding:
    """A single Skeptic finding stored in DuckDB."""

    id: str
    severity: str
    description: str
    requirement_ref: str | None
    spec_name: str
    task_group: str
    session_id: str
    superseded_by: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class VerificationResult:
    """A single Verifier verdict stored in DuckDB."""

    id: str
    requirement_id: str
    verdict: str
    evidence: str | None
    spec_name: str
    task_group: str
    session_id: str
    superseded_by: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class DriftFinding:
    """A single Oracle drift finding stored in DuckDB.

    Requirements: 32-REQ-6.3
    """

    id: str
    severity: str  # "critical" | "major" | "minor" | "observation"
    description: str
    spec_ref: str | None
    artifact_ref: str | None
    spec_name: str
    task_group: str
    session_id: str
    superseded_by: str | None = None
    created_at: datetime | None = None


def _new_id() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def insert_findings(
    conn: duckdb.DuckDBPyConnection,
    findings: list[ReviewFinding],
) -> int:
    """Insert findings, superseding existing active records for the same
    (spec_name, task_group). Returns count of inserted records.

    Requirements: 27-REQ-4.1, 27-REQ-4.3, 27-REQ-4.E1
    """
    if not findings:
        return 0

    spec_name = findings[0].spec_name
    task_group = findings[0].task_group
    session_id = findings[0].session_id

    # Supersede existing active records (27-REQ-4.1)
    existing = conn.execute(
        "SELECT id::VARCHAR FROM review_findings "
        "WHERE spec_name = ? AND task_group = ? AND superseded_by IS NULL",
        [spec_name, task_group],
    ).fetchall()

    superseded_ids = [row[0] for row in existing]

    if superseded_ids:
        conn.execute(
            "UPDATE review_findings SET superseded_by = ? "
            "WHERE spec_name = ? AND task_group = ? AND superseded_by IS NULL",
            [session_id, spec_name, task_group],
        )

    # Insert new records
    for f in findings:
        conn.execute(
            "INSERT INTO review_findings "
            "(id, severity, description, requirement_ref, spec_name, "
            "task_group, session_id, created_at) "
            "VALUES (?::UUID, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [
                f.id,
                f.severity,
                f.description,
                f.requirement_ref,
                f.spec_name,
                f.task_group,
                f.session_id,
            ],
        )

    # Insert causal links from superseded to new records (27-REQ-4.3)
    if superseded_ids:
        new_ids = [f.id for f in findings]
        for old_id in superseded_ids:
            for new_id in new_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO fact_causes (cause_id, effect_id) "
                    "VALUES (?::UUID, ?::UUID)",
                    [old_id, new_id],
                )

    logger.info(
        "Inserted %d review findings for %s/%s (superseded %d)",
        len(findings),
        spec_name,
        task_group,
        len(superseded_ids),
    )
    return len(findings)


def insert_verdicts(
    conn: duckdb.DuckDBPyConnection,
    verdicts: list[VerificationResult],
) -> int:
    """Insert verdicts, superseding existing active records for the same
    (spec_name, task_group). Returns count of inserted records.

    Requirements: 27-REQ-4.2, 27-REQ-4.3, 27-REQ-4.E1
    """
    if not verdicts:
        return 0

    spec_name = verdicts[0].spec_name
    task_group = verdicts[0].task_group
    session_id = verdicts[0].session_id

    # Supersede existing active records (27-REQ-4.2)
    existing = conn.execute(
        "SELECT id::VARCHAR FROM verification_results "
        "WHERE spec_name = ? AND task_group = ? AND superseded_by IS NULL",
        [spec_name, task_group],
    ).fetchall()

    superseded_ids = [row[0] for row in existing]

    if superseded_ids:
        conn.execute(
            "UPDATE verification_results SET superseded_by = ? "
            "WHERE spec_name = ? AND task_group = ? AND superseded_by IS NULL",
            [session_id, spec_name, task_group],
        )

    # Insert new records
    for v in verdicts:
        conn.execute(
            "INSERT INTO verification_results "
            "(id, requirement_id, verdict, evidence, spec_name, "
            "task_group, session_id, created_at) "
            "VALUES (?::UUID, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [
                v.id,
                v.requirement_id,
                v.verdict,
                v.evidence,
                v.spec_name,
                v.task_group,
                v.session_id,
            ],
        )

    # Insert causal links from superseded to new records (27-REQ-4.3)
    if superseded_ids:
        new_ids = [v.id for v in verdicts]
        for old_id in superseded_ids:
            for new_id in new_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO fact_causes (cause_id, effect_id) "
                    "VALUES (?::UUID, ?::UUID)",
                    [old_id, new_id],
                )

    logger.info(
        "Inserted %d verification results for %s/%s (superseded %d)",
        len(verdicts),
        spec_name,
        task_group,
        len(superseded_ids),
    )
    return len(verdicts)


def query_active_findings(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    task_group: str | None = None,
) -> list[ReviewFinding]:
    """Query non-superseded findings for a spec.

    Requirements: 27-REQ-5.1
    """
    if task_group is not None:
        rows = conn.execute(
            "SELECT id::VARCHAR, severity, description, requirement_ref, "
            "spec_name, task_group, session_id, superseded_by::VARCHAR, created_at "
            "FROM review_findings "
            "WHERE spec_name = ? AND task_group = ? AND superseded_by IS NULL "
            "ORDER BY severity, description",
            [spec_name, task_group],
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id::VARCHAR, severity, description, requirement_ref, "
            "spec_name, task_group, session_id, superseded_by::VARCHAR, created_at "
            "FROM review_findings "
            "WHERE spec_name = ? AND superseded_by IS NULL "
            "ORDER BY severity, description",
            [spec_name],
        ).fetchall()

    findings = [_row_to_finding(r) for r in rows]
    # Sort by severity priority then description
    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), f.description))
    return findings


def query_active_verdicts(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    task_group: str | None = None,
) -> list[VerificationResult]:
    """Query non-superseded verdicts for a spec.

    Requirements: 27-REQ-5.2
    """
    if task_group is not None:
        rows = conn.execute(
            "SELECT id::VARCHAR, requirement_id, verdict, evidence, "
            "spec_name, task_group, session_id, superseded_by::VARCHAR, created_at "
            "FROM verification_results "
            "WHERE spec_name = ? AND task_group = ? AND superseded_by IS NULL "
            "ORDER BY requirement_id",
            [spec_name, task_group],
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id::VARCHAR, requirement_id, verdict, evidence, "
            "spec_name, task_group, session_id, superseded_by::VARCHAR, created_at "
            "FROM verification_results "
            "WHERE spec_name = ? AND superseded_by IS NULL "
            "ORDER BY requirement_id",
            [spec_name],
        ).fetchall()

    return [_row_to_verdict(r) for r in rows]


def query_findings_by_session(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
) -> list[ReviewFinding]:
    """Query all findings for a specific session (for convergence).

    Requirements: 27-REQ-6.1
    """
    rows = conn.execute(
        "SELECT id::VARCHAR, severity, description, requirement_ref, "
        "spec_name, task_group, session_id, superseded_by::VARCHAR, created_at "
        "FROM review_findings WHERE session_id = ? "
        "ORDER BY severity, description",
        [session_id],
    ).fetchall()

    findings = [_row_to_finding(r) for r in rows]
    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), f.description))
    return findings


def query_verdicts_by_session(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
) -> list[VerificationResult]:
    """Query all verdicts for a specific session (for convergence).

    Requirements: 27-REQ-6.2
    """
    rows = conn.execute(
        "SELECT id::VARCHAR, requirement_id, verdict, evidence, "
        "spec_name, task_group, session_id, superseded_by::VARCHAR, created_at "
        "FROM verification_results WHERE session_id = ? "
        "ORDER BY requirement_id",
        [session_id],
    ).fetchall()

    return [_row_to_verdict(r) for r in rows]


def _row_to_finding(row: tuple) -> ReviewFinding:
    """Convert a DB row to a ReviewFinding."""
    return ReviewFinding(
        id=row[0],
        severity=row[1],
        description=row[2],
        requirement_ref=row[3],
        spec_name=row[4],
        task_group=row[5],
        session_id=row[6],
        superseded_by=row[7],
        created_at=row[8],
    )


def _row_to_verdict(row: tuple) -> VerificationResult:
    """Convert a DB row to a VerificationResult."""
    return VerificationResult(
        id=row[0],
        requirement_id=row[1],
        verdict=row[2],
        evidence=row[3],
        spec_name=row[4],
        task_group=row[5],
        session_id=row[6],
        superseded_by=row[7],
        created_at=row[8],
    )
