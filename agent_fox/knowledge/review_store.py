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


# ---------------------------------------------------------------------------
# Shared insert-with-supersession helpers
# ---------------------------------------------------------------------------


def _supersede_active_records(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    spec_name: str,
    task_group: str,
    marker: str,
) -> list[str]:
    """Mark active records as superseded. Returns list of superseded IDs."""
    existing = conn.execute(
        f"SELECT id::VARCHAR FROM {table} "  # noqa: S608
        "WHERE spec_name = ? AND task_group = ? AND superseded_by IS NULL",
        [spec_name, task_group],
    ).fetchall()

    superseded_ids = [row[0] for row in existing]

    if superseded_ids:
        conn.execute(
            f"UPDATE {table} SET superseded_by = ? "  # noqa: S608
            "WHERE spec_name = ? AND task_group = ? AND superseded_by IS NULL",
            [marker, spec_name, task_group],
        )

    return superseded_ids


def _insert_causal_links(
    conn: duckdb.DuckDBPyConnection,
    superseded_ids: list[str],
    new_ids: list[str],
) -> None:
    """Insert causal links from superseded to new records (27-REQ-4.3)."""
    for old_id in superseded_ids:
        for new_id in new_ids:
            conn.execute(
                "INSERT OR IGNORE INTO fact_causes (cause_id, effect_id) "
                "VALUES (?::UUID, ?::UUID)",
                [old_id, new_id],
            )


def _insert_with_supersession(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    columns: str,
    records: list,
    value_extractor: callable,
    record_type_label: str,
) -> int:
    """Insert records with supersession and causal links.

    Shared logic for insert_findings and insert_verdicts.
    """
    if not records:
        return 0

    spec_name = records[0].spec_name
    task_group = records[0].task_group
    session_id = records[0].session_id

    superseded_ids = _supersede_active_records(
        conn, table, spec_name, task_group, session_id
    )

    placeholders = ", ".join("?" for _ in columns.split(", "))
    for r in records:
        conn.execute(
            f"INSERT INTO {table} ({columns}, created_at) "  # noqa: S608
            f"VALUES ({placeholders}, CURRENT_TIMESTAMP)",
            value_extractor(r),
        )

    if superseded_ids:
        _insert_causal_links(conn, superseded_ids, [r.id for r in records])

    logger.info(
        "Inserted %d %s for %s/%s (superseded %d)",
        len(records),
        record_type_label,
        spec_name,
        task_group,
        len(superseded_ids),
    )
    return len(records)


# ---------------------------------------------------------------------------
# Insert functions
# ---------------------------------------------------------------------------


def insert_findings(
    conn: duckdb.DuckDBPyConnection,
    findings: list[ReviewFinding],
) -> int:
    """Insert findings, superseding existing active records for the same
    (spec_name, task_group). Returns count of inserted records.

    Requirements: 27-REQ-4.1, 27-REQ-4.3, 27-REQ-4.E1
    """
    return _insert_with_supersession(
        conn,
        table="review_findings",
        columns=(
            "id, severity, description, requirement_ref,"
            " spec_name, task_group, session_id"
        ),
        records=findings,
        value_extractor=lambda f: [
            f.id,
            f.severity,
            f.description,
            f.requirement_ref,
            f.spec_name,
            f.task_group,
            f.session_id,
        ],
        record_type_label="review findings",
    )


def insert_verdicts(
    conn: duckdb.DuckDBPyConnection,
    verdicts: list[VerificationResult],
) -> int:
    """Insert verdicts, superseding existing active records for the same
    (spec_name, task_group). Returns count of inserted records.

    Requirements: 27-REQ-4.2, 27-REQ-4.3, 27-REQ-4.E1
    """
    return _insert_with_supersession(
        conn,
        table="verification_results",
        columns=(
            "id, requirement_id, verdict, evidence, spec_name, task_group, session_id"
        ),
        records=verdicts,
        value_extractor=lambda v: [
            v.id,
            v.requirement_id,
            v.verdict,
            v.evidence,
            v.spec_name,
            v.task_group,
            v.session_id,
        ],
        record_type_label="verification results",
    )


def insert_drift_findings(
    conn: duckdb.DuckDBPyConnection,
    findings: list[DriftFinding],
) -> int:
    """Insert drift findings, superseding existing active records for the same
    (spec_name, task_group). Returns count of inserted records.

    Requirements: 32-REQ-7.1, 32-REQ-7.3, 32-REQ-7.E1
    """
    if not findings:
        return 0

    spec_name = findings[0].spec_name
    task_group = findings[0].task_group

    try:
        # Supersede existing active records (32-REQ-7.3)
        # Use the first new finding's ID as the supersession marker.
        supersession_id = findings[0].id
        conn.execute(
            "UPDATE drift_findings SET superseded_by = ?::UUID "
            "WHERE spec_name = ? AND task_group = ? AND superseded_by IS NULL",
            [supersession_id, spec_name, task_group],
        )

        # Insert new records
        for f in findings:
            conn.execute(
                "INSERT INTO drift_findings "
                "(id, severity, description, spec_ref, artifact_ref, spec_name, "
                "task_group, session_id, created_at) "
                "VALUES (?::UUID, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                [
                    f.id,
                    f.severity,
                    f.description,
                    f.spec_ref,
                    f.artifact_ref,
                    f.spec_name,
                    f.task_group,
                    f.session_id,
                ],
            )
    except Exception as exc:
        logger.warning("Failed to insert drift findings: %s", exc)
        return 0

    logger.info(
        "Inserted %d drift findings for %s/%s",
        len(findings),
        spec_name,
        task_group,
    )
    return len(findings)


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------


def _query_active(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    columns: str,
    spec_name: str,
    task_group: str | None,
    order_by: str,
) -> list[tuple]:
    """Query non-superseded records with optional task_group filter."""
    if task_group is not None:
        return conn.execute(
            f"SELECT {columns} FROM {table} "  # noqa: S608
            "WHERE spec_name = ? AND task_group = ? AND superseded_by IS NULL "
            f"ORDER BY {order_by}",
            [spec_name, task_group],
        ).fetchall()
    return conn.execute(
        f"SELECT {columns} FROM {table} "  # noqa: S608
        "WHERE spec_name = ? AND superseded_by IS NULL "
        f"ORDER BY {order_by}",
        [spec_name],
    ).fetchall()


_FINDING_COLS = (
    "id::VARCHAR, severity, description, requirement_ref, "
    "spec_name, task_group, session_id, superseded_by::VARCHAR, created_at"
)

_VERDICT_COLS = (
    "id::VARCHAR, requirement_id, verdict, evidence, "
    "spec_name, task_group, session_id, superseded_by::VARCHAR, created_at"
)

_DRIFT_COLS = (
    "id::VARCHAR, severity, description, spec_ref, artifact_ref, "
    "spec_name, task_group, session_id, superseded_by::VARCHAR, created_at"
)


def query_active_findings(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    task_group: str | None = None,
) -> list[ReviewFinding]:
    """Query non-superseded findings for a spec.

    Requirements: 27-REQ-5.1
    """
    rows = _query_active(
        conn,
        "review_findings",
        _FINDING_COLS,
        spec_name,
        task_group,
        "severity, description",
    )
    findings = [_row_to_finding(r) for r in rows]
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
    rows = _query_active(
        conn,
        "verification_results",
        _VERDICT_COLS,
        spec_name,
        task_group,
        "requirement_id",
    )
    return [_row_to_verdict(r) for r in rows]


def query_findings_by_session(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
) -> list[ReviewFinding]:
    """Query all findings for a specific session (for convergence).

    Requirements: 27-REQ-6.1
    """
    rows = conn.execute(
        f"SELECT {_FINDING_COLS} "
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
        f"SELECT {_VERDICT_COLS} "
        "FROM verification_results WHERE session_id = ? "
        "ORDER BY requirement_id",
        [session_id],
    ).fetchall()

    return [_row_to_verdict(r) for r in rows]


def query_active_drift_findings(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    task_group: str | None = None,
) -> list[DriftFinding]:
    """Query non-superseded drift findings for a spec, sorted by severity.

    Requirements: 32-REQ-7.4
    """
    rows = _query_active(
        conn,
        "drift_findings",
        _DRIFT_COLS,
        spec_name,
        task_group,
        "severity, description",
    )
    findings = [_row_to_drift_finding(r) for r in rows]
    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), f.description))
    return findings


# ---------------------------------------------------------------------------
# Row converters
# ---------------------------------------------------------------------------


def _row_to_drift_finding(row: tuple) -> DriftFinding:
    """Convert a DB row to a DriftFinding."""
    return DriftFinding(
        id=row[0],
        severity=row[1],
        description=row[2],
        spec_ref=row[3],
        artifact_ref=row[4],
        spec_name=row[5],
        task_group=row[6],
        session_id=row[7],
        superseded_by=row[8],
        created_at=row[9],
    )


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
