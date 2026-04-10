"""Record session outcomes, prompt texts, and scope check results to DuckDB.

Requirements: 87-REQ-2.5, 87-REQ-4.1 through 87-REQ-4.4, 87-REQ-5.1 through 87-REQ-5.3
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import duckdb

from agent_fox.scope_guard.models import (
    PromptRecord,
    ScopeCheckResult,
    ScopeGuardSessionOutcome,
    SpecWasteSummary,
    WasteReport,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROMPT_MAX_LENGTH = 100_000
_PROMPT_KEEP_CHARS = 500
_TRUNCATION_MARKER = "\n...[TRUNCATED]...\n"
_STUB_DIRECTIVE_TAG = "SCOPE_GUARD:STUB_ONLY"


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create scope_guard telemetry tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_outcomes (
            session_id          VARCHAR PRIMARY KEY,
            spec_number         INTEGER NOT NULL,
            task_group_number   INTEGER NOT NULL,
            classification      VARCHAR NOT NULL,
            duration_seconds    DOUBLE NOT NULL,
            cost_dollars        DOUBLE NOT NULL,
            timestamp           TIMESTAMP NOT NULL,
            stub_violation      BOOLEAN DEFAULT FALSE,
            violation_details   JSON,
            reason              VARCHAR DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_prompts (
            session_id              VARCHAR PRIMARY KEY,
            prompt_text             TEXT NOT NULL,
            truncated               BOOLEAN DEFAULT FALSE,
            stub_directive_present  BOOLEAN NOT NULL,
            timestamp               TIMESTAMP NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scope_check_results (
            id                  INTEGER PRIMARY KEY,
            spec_number         INTEGER NOT NULL,
            task_group_number   INTEGER NOT NULL,
            overall_status      VARCHAR NOT NULL,
            deliverable_count   INTEGER NOT NULL,
            check_duration_ms   INTEGER NOT NULL,
            deliverable_results JSON NOT NULL,
            timestamp           TIMESTAMP NOT NULL
        )
    """)
    # Auto-increment helper: DuckDB uses sequences
    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS scope_check_id_seq START 1
    """)


# ---------------------------------------------------------------------------
# Session outcome recording  (87-REQ-4.1, 87-REQ-4.2, 87-REQ-4.3)
# ---------------------------------------------------------------------------


def record_session_outcome(conn: duckdb.DuckDBPyConnection, outcome: ScopeGuardSessionOutcome) -> None:
    """Insert a session outcome record into the telemetry store."""
    violation_details_json: str | None = None
    if outcome.violation_details:
        violation_details_json = json.dumps(
            [
                {
                    "file_path": v.file_path,
                    "function_id": v.function_id,
                    "body_preview": v.body_preview,
                    "prompt_directive_present": v.prompt_directive_present,
                }
                for v in outcome.violation_details
            ]
        )

    conn.execute(
        """
        INSERT INTO session_outcomes (
            session_id, spec_number, task_group_number, classification,
            duration_seconds, cost_dollars, timestamp, stub_violation,
            violation_details, reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            outcome.session_id,
            outcome.spec_number,
            outcome.task_group_number,
            outcome.classification.value,
            outcome.duration_seconds,
            outcome.cost_dollars,
            outcome.timestamp,
            outcome.stub_violation,
            violation_details_json,
            outcome.reason,
        ],
    )


# ---------------------------------------------------------------------------
# Prompt persistence and retrieval  (87-REQ-5.1, 87-REQ-5.2, 87-REQ-5.3)
# ---------------------------------------------------------------------------


def persist_prompt(conn: duckdb.DuckDBPyConnection, session_id: str, prompt_text: str) -> None:
    """Store a session prompt with truncation logic.

    If prompt exceeds _PROMPT_MAX_LENGTH characters, retain the first and last
    _PROMPT_KEEP_CHARS characters separated by a truncation marker, and set the
    truncated flag.  (87-REQ-5.E1)
    """
    truncated = len(prompt_text) > _PROMPT_MAX_LENGTH
    if truncated:
        stored_text = prompt_text[:_PROMPT_KEEP_CHARS] + _TRUNCATION_MARKER + prompt_text[-_PROMPT_KEEP_CHARS:]
    else:
        stored_text = prompt_text

    directive_present = _STUB_DIRECTIVE_TAG in stored_text

    conn.execute(
        """
        INSERT INTO session_prompts (
            session_id, prompt_text, truncated, stub_directive_present, timestamp
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            session_id,
            stored_text,
            truncated,
            directive_present,
            datetime.now(UTC),
        ],
    )


def get_session_prompt(conn: duckdb.DuckDBPyConnection, session_id: str) -> PromptRecord | None:
    """Retrieve a session prompt record."""
    rows = conn.execute(
        "SELECT session_id, prompt_text, truncated, stub_directive_present FROM session_prompts WHERE session_id = ?",
        [session_id],
    ).fetchall()
    if not rows:
        return None
    row = rows[0]
    return PromptRecord(
        session_id=row[0],
        prompt_text=row[1],
        truncated=row[2],
        stub_directive_present=row[3],
    )


# ---------------------------------------------------------------------------
# Scope check recording  (87-REQ-2.5)
# ---------------------------------------------------------------------------


def record_scope_check(conn: duckdb.DuckDBPyConnection, result: ScopeCheckResult) -> None:
    """Record a scope check result in the telemetry store."""
    deliverable_results_json = json.dumps(
        [
            {
                "file_path": dr.deliverable.file_path,
                "function_id": dr.deliverable.function_id,
                "task_group_number": dr.deliverable.task_group_number,
                "status": dr.status.value,
                "reason": dr.reason,
            }
            for dr in result.deliverable_results
        ]
    )

    # Derive spec_number from first deliverable if available, else 0
    spec_number = 0
    if result.deliverable_results:
        spec_number = result.deliverable_results[0].deliverable.task_group_number

    next_id = conn.execute("SELECT nextval('scope_check_id_seq')").fetchone()
    assert next_id is not None
    row_id = next_id[0]

    conn.execute(
        """
        INSERT INTO scope_check_results (
            id, spec_number, task_group_number, overall_status,
            deliverable_count, check_duration_ms, deliverable_results, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            row_id,
            spec_number,
            result.task_group_number,
            result.overall,
            result.deliverable_count,
            result.check_duration_ms,
            deliverable_results_json,
            datetime.now(UTC),
        ],
    )


# ---------------------------------------------------------------------------
# Waste reporting  (87-REQ-4.4)
# ---------------------------------------------------------------------------


def query_waste_report(conn: duckdb.DuckDBPyConnection, spec_number: int | None = None) -> WasteReport:
    """Query aggregate waste report for no-op and pre-flight-skip sessions."""
    where_clause = ""
    params: list[object] = []
    if spec_number is not None:
        where_clause = "AND spec_number = ?"
        params.append(spec_number)

    rows = conn.execute(
        f"""
        SELECT
            spec_number,
            COUNT(*) FILTER (WHERE classification = 'no-op') AS no_op_count,
            COUNT(*) FILTER (WHERE classification = 'pre-flight-skip') AS pre_flight_skip_count,
            COALESCE(SUM(cost_dollars) FILTER (
                WHERE classification IN ('no-op', 'pre-flight-skip')
            ), 0) AS total_wasted_cost,
            COALESCE(SUM(duration_seconds) FILTER (
                WHERE classification IN ('no-op', 'pre-flight-skip')
            ), 0) AS total_wasted_duration
        FROM session_outcomes
        WHERE classification IN ('no-op', 'pre-flight-skip')
        {where_clause}
        GROUP BY spec_number
        ORDER BY spec_number
        """,
        params,
    ).fetchall()

    per_spec = [
        SpecWasteSummary(
            spec_number=row[0],
            no_op_count=row[1],
            pre_flight_skip_count=row[2],
            total_wasted_cost=row[3],
            total_wasted_duration=row[4],
        )
        for row in rows
    ]
    return WasteReport(per_spec=per_spec)
