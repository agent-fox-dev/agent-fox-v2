"""CRUD operations for review_findings and verification_results tables.

Provides insert-with-supersession, active-record queries, and
session-scoped queries for convergence.

Requirements: 27-REQ-1.1, 27-REQ-2.1, 27-REQ-4.1, 27-REQ-4.2, 27-REQ-4.3,
              27-REQ-4.E1, 27-REQ-5.1, 27-REQ-5.2, 27-REQ-6.1, 27-REQ-6.2
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import duckdb  # noqa: F401

logger = logging.getLogger(__name__)

VALID_SEVERITIES = {"critical", "major", "minor", "observation"}
VALID_VERDICTS = {"PASS", "FAIL"}

# Only these severities are actionable and persisted to review_findings.
# ``minor`` and ``observation`` have no downstream consumers so they are
# dropped at write time to avoid storing dead rows (issue #553).
ACTIONABLE_SEVERITIES: frozenset[str] = frozenset({"critical", "major"})

# Defense-in-depth: only these table names may be interpolated into SQL.
_ALLOWED_TABLES: frozenset[str] = frozenset({"review_findings", "drift_findings", "verification_results"})


def _validate_table_name(table: str) -> None:
    """Raise ValueError if *table* is not in the allowlist."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Table {table!r} is not in the allowed set: {sorted(_ALLOWED_TABLES)}")


_SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2, "observation": 3}


def normalize_severity(severity: str) -> str:
    """Normalize severity to a valid value.

    Lowercases and strips the input. Returns ``"observation"`` with a
    warning log if the value is not recognised.

    Requirements: 27-REQ-3.E2
    """
    normalized = severity.lower().strip()
    if normalized in VALID_SEVERITIES:
        return normalized
    logger.warning("Unknown severity '%s', normalizing to 'observation'", severity)
    return "observation"


def validate_verdict(verdict: str) -> str:
    """Normalize and validate a verdict value.

    Upper-cases and strips the input. Returns the normalised value if
    valid (``PASS`` or ``FAIL``). Non-standard values (e.g. ``PARTIAL``,
    ``CONDITIONAL``) are mapped to ``"FAIL"`` and a warning is logged,
    so that partial compliance is treated as non-compliance rather than
    silently dropped.
    """
    normalized = verdict.upper().strip()
    if normalized in VALID_VERDICTS:
        return normalized
    logger.warning(
        "Invalid verdict '%s' normalized to 'FAIL' (must be PASS or FAIL)",
        verdict,
    )
    return "FAIL"


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
    category: str | None = None


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
    _validate_table_name(table)
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


def _insert_with_supersession(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    columns: str,
    records: list,
    value_extractor: Callable[..., list[Any]],
    record_type_label: str,
) -> int:
    """Insert records with supersession.

    Shared logic for insert_findings, insert_verdicts, and
    insert_drift_findings.  Old records are marked via the
    ``superseded_by`` column; no causal links are written.

    Requirements: 116-REQ-5.1, 116-REQ-5.2
    """
    _validate_table_name(table)
    if not records:
        return 0

    spec_name = records[0].spec_name
    session_id = records[0].session_id

    # Supersede existing active records per task_group. A batch may span
    # multiple task_groups (e.g. cross-group findings), so we supersede each
    # distinct task_group found in the batch rather than only the first.
    superseded_ids: list[str] = []
    seen_task_groups: set[str] = set()
    for r in records:
        tg = r.task_group
        if tg not in seen_task_groups:
            seen_task_groups.add(tg)
            superseded_ids.extend(_supersede_active_records(conn, table, r.spec_name, tg, session_id))

    placeholders = ", ".join("?" for _ in columns.split(", "))
    for r in records:
        conn.execute(
            f"INSERT INTO {table} ({columns}, created_at) "  # noqa: S608
            f"VALUES ({placeholders}, CURRENT_TIMESTAMP)",
            value_extractor(r),
        )

    task_groups_label = ", ".join(sorted(seen_task_groups))
    logger.info(
        "Inserted %d %s for %s/[%s] (superseded %d)",
        len(records),
        record_type_label,
        spec_name,
        task_groups_label,
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

    Only ``critical`` and ``major`` findings are persisted.  ``minor`` and
    ``observation`` findings are silently dropped before the write — they
    have no downstream consumers and storing them wastes I/O (issue #553).

    Requirements: 27-REQ-4.1, 27-REQ-4.3, 27-REQ-4.E1
    """
    actionable = [f for f in findings if f.severity in ACTIONABLE_SEVERITIES]
    if len(actionable) < len(findings):
        logger.debug(
            "Dropping %d non-actionable finding(s) (minor/observation) before insert",
            len(findings) - len(actionable),
        )
    return _insert_with_supersession(
        conn,
        table="review_findings",
        columns=("id, severity, description, requirement_ref, spec_name, task_group, session_id, category"),
        records=actionable,
        value_extractor=lambda f: [
            f.id,
            f.severity,
            f.description,
            f.requirement_ref,
            f.spec_name,
            f.task_group,
            f.session_id,
            f.category,
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
        columns=("id, requirement_id, verdict, evidence, spec_name, task_group, session_id"),
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
    try:
        return _insert_with_supersession(
            conn,
            table="drift_findings",
            columns=("id, severity, description, spec_ref, artifact_ref, spec_name, task_group, session_id"),
            records=findings,
            value_extractor=lambda f: [
                f.id,
                f.severity,
                f.description,
                f.spec_ref,
                f.artifact_ref,
                f.spec_name,
                f.task_group,
                f.session_id,
            ],
            record_type_label="drift findings",
        )
    except Exception as exc:
        logger.warning("Failed to insert drift findings: %s", exc)
        return 0


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
    "spec_name, task_group, session_id, superseded_by::VARCHAR, created_at, category"
)

_VERDICT_COLS = (
    "id::VARCHAR, requirement_id, verdict, evidence, "
    "spec_name, task_group, session_id, superseded_by::VARCHAR, created_at"
)

_DRIFT_COLS = (
    "id::VARCHAR, severity, description, spec_ref, artifact_ref, "
    "spec_name, task_group, session_id, superseded_by::VARCHAR, created_at"
)


def query_cross_group_findings(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    task_group: str,
    exclude_prereview: bool = False,
) -> list[ReviewFinding]:
    """Query non-superseded actionable findings from *other* task groups.

    Returns findings where ``task_group != ?`` — i.e. everything except the
    caller's own group.  Only ``critical`` and ``major`` findings are returned.

    When *exclude_prereview* is ``True``, group ``"0"`` findings are also
    excluded.  This prevents duplication when group 0 findings have been
    elevated into the primary review results (120-REQ-2.3).
    """
    if exclude_prereview:
        rows = conn.execute(
            f"SELECT {_FINDING_COLS} FROM review_findings "  # noqa: S608
            "WHERE spec_name = ? AND task_group != ? AND task_group != '0' "
            "AND superseded_by IS NULL "
            "ORDER BY severity, description",
            [spec_name, task_group],
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT {_FINDING_COLS} FROM review_findings "  # noqa: S608
            "WHERE spec_name = ? AND task_group != ? AND superseded_by IS NULL "
            "ORDER BY severity, description",
            [spec_name, task_group],
        ).fetchall()
    findings = [_row_to_finding(r) for r in rows if r[1] in ACTIONABLE_SEVERITIES]
    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), f.description))
    return findings


def query_cross_group_verdicts(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    task_group: str,
) -> list[VerificationResult]:
    """Query non-superseded verdicts from *other* task groups.

    Returns verdicts where ``task_group != ?``.
    """
    rows = conn.execute(
        f"SELECT {_VERDICT_COLS} FROM verification_results "  # noqa: S608
        "WHERE spec_name = ? AND task_group != ? AND superseded_by IS NULL "
        "ORDER BY requirement_id",
        [spec_name, task_group],
    ).fetchall()
    return [_row_to_verdict(r) for r in rows]


def query_active_findings(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    task_group: str | None = None,
    include_prereview: bool = False,
) -> list[ReviewFinding]:
    """Query non-superseded actionable findings for a spec.

    Returns only ``critical`` and ``major`` findings.  ``minor`` and
    ``observation`` rows are excluded as a defense-in-depth guard against
    any legacy rows that may have been written before issue #553 was fixed.

    When *include_prereview* is ``True`` and *task_group* is not ``None``
    and not ``"0"``, findings from both the requested task group and group
    ``"0"`` (pre-review) are returned.  This elevates pre-review findings
    into the primary review results so they are tracked via
    ``finding_injections`` and can be superseded on session completion.

    Requirements: 27-REQ-5.1, 120-REQ-2.1
    """
    if include_prereview and task_group is not None and task_group != "0":
        # Include both the requested task group and group 0 (pre-review)
        rows = conn.execute(
            f"SELECT {_FINDING_COLS} FROM review_findings "  # noqa: S608
            "WHERE spec_name = ? AND task_group IN (?, '0') AND superseded_by IS NULL "
            "ORDER BY severity, description",
            [spec_name, task_group],
        ).fetchall()
    else:
        rows = _query_active(
            conn,
            "review_findings",
            _FINDING_COLS,
            spec_name,
            task_group,
            "severity, description",
        )
    findings = [_row_to_finding(r) for r in rows if r[1] in ACTIONABLE_SEVERITIES]
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
        f"SELECT {_FINDING_COLS} FROM review_findings WHERE session_id = ? ORDER BY severity, description",
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
        f"SELECT {_VERDICT_COLS} FROM verification_results WHERE session_id = ? ORDER BY requirement_id",
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
        category=row[9] if len(row) > 9 else None,
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


# ---------------------------------------------------------------------------
# Injection tracking (issue #558)
# ---------------------------------------------------------------------------


def record_finding_injections(
    conn: duckdb.DuckDBPyConnection,
    finding_ids: list[str],
    session_id: str,
) -> None:
    """Record which finding/verdict IDs were injected into a session.

    Each (finding_id, session_id) pair is recorded at most once — duplicate
    calls (e.g. when retrieve() is invoked twice for the same session) are
    silently ignored.  A missing ``finding_injections`` table (pre-v23 DB)
    is handled gracefully by logging a warning and returning.

    Requirements: 558-AC-1
    """
    if not finding_ids:
        return
    for finding_id in finding_ids:
        existing = conn.execute(
            "SELECT 1 FROM finding_injections WHERE finding_id = ? AND session_id = ?",
            [finding_id, session_id],
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO finding_injections (id, finding_id, session_id, injected_at) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                [str(uuid.uuid4()), finding_id, session_id],
            )
    logger.debug(
        "Recorded %d injection(s) for session %s",
        len(finding_ids),
        session_id,
    )


def _get_run_start_local(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
) -> datetime | None:
    """Return the ``started_at`` of *run_id* converted to DuckDB-local time.

    ``runs.started_at`` is stored as a Python-UTC ISO string (via
    ``datetime.now(UTC).isoformat()``).  ``review_findings.created_at``
    uses DuckDB's ``CURRENT_TIMESTAMP`` which resolves to the server's
    local time (issue #480).  To compare the two correctly we must
    convert the UTC value to local time in Python.

    Returns ``None`` when *run_id* is not found.
    """
    row = conn.execute(
        "SELECT started_at FROM runs WHERE id = ?",
        [run_id],
    ).fetchone()
    if row is None:
        return None

    started_at = row[0]
    # DuckDB returns a naive datetime (TIMESTAMP column).  The value was
    # written by ``datetime.now(UTC).isoformat()`` so it *is* UTC, but
    # DuckDB stripped the +00:00 on CAST.  Re-attach UTC then convert to
    # local time and strip tzinfo so it's comparable to CURRENT_TIMESTAMP.
    if isinstance(started_at, datetime):
        utc_dt = started_at.replace(tzinfo=UTC)
        local_dt = utc_dt.astimezone()  # system local timezone
        return local_dt.replace(tzinfo=None)
    # Fallback: if it's a string, parse it
    dt = datetime.fromisoformat(str(started_at))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    local_dt = dt.astimezone()
    return local_dt.replace(tzinfo=None)


def query_prior_run_findings(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    current_run_id: str,
    max_items: int = 5,
) -> list[ReviewFinding]:
    """Query active critical/major findings from prior runs.

    Returns findings that:
    - belong to the specified spec
    - are not superseded (``superseded_by IS NULL``)
    - have severity ``critical`` or ``major``
    - were created before the current run's ``started_at`` timestamp

    Results are sorted by severity (critical first), then description,
    and capped at *max_items*.

    Handles missing ``review_findings`` or ``runs`` tables gracefully
    by returning an empty list (120-REQ-4.E3).

    Requirements: 120-REQ-4.1, 120-REQ-4.3, 120-REQ-4.E1, 120-REQ-4.E2, 120-REQ-4.E3
    """
    try:
        cutoff = _get_run_start_local(conn, current_run_id)
        if cutoff is None:
            return []

        rows = conn.execute(
            f"SELECT {_FINDING_COLS} FROM review_findings "  # noqa: S608
            "WHERE spec_name = ? "
            "AND superseded_by IS NULL "
            "AND severity IN ('critical', 'major') "
            "AND created_at < ? "
            "ORDER BY CASE severity WHEN 'critical' THEN 0 ELSE 1 END, description "
            "LIMIT ?",
            [spec_name, cutoff, max_items],
        ).fetchall()
        return [_row_to_finding(r) for r in rows]
    except Exception:
        logger.debug(
            "Could not query prior-run findings for %s (table may not exist)",
            spec_name,
        )
        return []


def query_prior_run_verdicts(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    current_run_id: str,
    max_items: int = 5,
) -> list[VerificationResult]:
    """Query active FAIL verdicts from prior runs.

    Returns verdicts that:
    - belong to the specified spec
    - are not superseded (``superseded_by IS NULL``)
    - have verdict ``FAIL``
    - were created before the current run's ``started_at`` timestamp

    Results are sorted by requirement_id and capped at *max_items*.

    Handles missing tables gracefully by returning an empty list
    (120-REQ-4.E3).

    Requirements: 120-REQ-4.5, 120-REQ-4.E1, 120-REQ-4.E3
    """
    try:
        cutoff = _get_run_start_local(conn, current_run_id)
        if cutoff is None:
            return []

        rows = conn.execute(
            f"SELECT {_VERDICT_COLS} FROM verification_results "  # noqa: S608
            "WHERE spec_name = ? "
            "AND superseded_by IS NULL "
            "AND verdict = 'FAIL' "
            "AND created_at < ? "
            "ORDER BY requirement_id "
            "LIMIT ?",
            [spec_name, cutoff, max_items],
        ).fetchall()
        return [_row_to_verdict(r) for r in rows]
    except Exception:
        logger.debug(
            "Could not query prior-run verdicts for %s (table may not exist)",
            spec_name,
        )
        return []


def dismiss_finding_by_id(
    conn: duckdb.DuckDBPyConnection,
    finding_id: str,
    reason: str,
) -> str | None:
    """Manually supersede a finding by ID across all three finding tables.

    Sets ``superseded_by`` to ``dismissed:<ISO-timestamp>`` on the matching
    active row (``superseded_by IS NULL``) in ``review_findings``,
    ``drift_findings``, or ``verification_results``, whichever contains the
    record.  Only active rows are dismissed; already-superseded rows are
    treated as "not found".

    Args:
        conn: DuckDB connection.
        finding_id: String representation of the finding UUID.
        reason: Human-readable reason for dismissal (logged but not stored
            in the DB schema — the ``dismissed:`` marker in ``superseded_by``
            encodes the action and timestamp).

    Returns:
        A human-readable description of the dismissed finding (e.g.
        ``"[critical] Missing error handling"``), or ``None`` if the ID is
        not found as an active row in any table.

    Requirements: 592-AC-1, 592-AC-2
    """
    marker = f"dismissed:{datetime.now(UTC).isoformat()}"

    # Try review_findings (skeptic archetype)
    row = conn.execute(
        "SELECT description, severity FROM review_findings "  # noqa: S608
        "WHERE id::VARCHAR = ? AND superseded_by IS NULL",
        [finding_id],
    ).fetchone()
    if row is not None:
        description, severity = row
        conn.execute(
            "UPDATE review_findings SET superseded_by = ? "
            "WHERE id::VARCHAR = ? AND superseded_by IS NULL",
            [marker, finding_id],
        )
        logger.info(
            "Dismissed review finding %s (%s): %s [reason: %s]",
            finding_id,
            severity,
            description,
            reason,
        )
        return f"[{severity}] {description}"

    # Try drift_findings (oracle archetype)
    row = conn.execute(
        "SELECT description, severity FROM drift_findings "  # noqa: S608
        "WHERE id::VARCHAR = ? AND superseded_by IS NULL",
        [finding_id],
    ).fetchone()
    if row is not None:
        description, severity = row
        conn.execute(
            "UPDATE drift_findings SET superseded_by = ? "
            "WHERE id::VARCHAR = ? AND superseded_by IS NULL",
            [marker, finding_id],
        )
        logger.info(
            "Dismissed drift finding %s (%s): %s [reason: %s]",
            finding_id,
            severity,
            description,
            reason,
        )
        return f"[{severity}] {description}"

    # Try verification_results (verifier archetype)
    row = conn.execute(
        "SELECT requirement_id, verdict FROM verification_results "  # noqa: S608
        "WHERE id::VARCHAR = ? AND superseded_by IS NULL",
        [finding_id],
    ).fetchone()
    if row is not None:
        requirement_id, verdict = row
        conn.execute(
            "UPDATE verification_results SET superseded_by = ? "
            "WHERE id::VARCHAR = ? AND superseded_by IS NULL",
            [marker, finding_id],
        )
        logger.info(
            "Dismissed verification result %s (%s): %s [reason: %s]",
            finding_id,
            verdict,
            requirement_id,
            reason,
        )
        return f"[{verdict}] {requirement_id}"

    return None


def supersede_injected_findings(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
) -> None:
    """Supersede all review findings and verdicts injected into a completed session.

    Looks up the finding_injections table for the given session_id, then marks
    each referenced row in ``review_findings`` and ``verification_results`` as
    superseded (sets ``superseded_by`` to the session_id string).  Only rows
    that are still active (``superseded_by IS NULL``) are updated.

    A missing ``finding_injections`` table (pre-v23 DB) raises no exception —
    the caller is responsible for catching and logging the error.

    Requirements: 558-AC-2
    """
    rows = conn.execute(
        "SELECT finding_id FROM finding_injections WHERE session_id = ?",
        [session_id],
    ).fetchall()
    finding_ids = [row[0] for row in rows]

    if not finding_ids:
        logger.debug("No injected findings to supersede for session %s", session_id)
        return

    marker = session_id
    for finding_id in finding_ids:
        conn.execute(
            "UPDATE review_findings SET superseded_by = ? WHERE id::VARCHAR = ? AND superseded_by IS NULL",
            [marker, finding_id],
        )
        conn.execute(
            "UPDATE verification_results SET superseded_by = ? WHERE id::VARCHAR = ? AND superseded_by IS NULL",
            [marker, finding_id],
        )

    logger.info(
        "Superseded %d injected finding(s) for completed session %s",
        len(finding_ids),
        session_id,
    )
