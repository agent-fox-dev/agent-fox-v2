"""Record session outcomes, prompt texts, and scope check results to DuckDB.

Requirements: 87-REQ-2.5, 87-REQ-4.1 through 87-REQ-4.4, 87-REQ-5.1 through 87-REQ-5.3
"""

from __future__ import annotations

import duckdb

from agent_fox.scope_guard.models import (
    PromptRecord,
    ScopeCheckResult,
    ScopeGuardSessionOutcome,
    WasteReport,
)


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create scope_guard telemetry tables if they don't exist."""
    raise NotImplementedError


def record_session_outcome(
    conn: duckdb.DuckDBPyConnection, outcome: ScopeGuardSessionOutcome
) -> None:
    """Insert a session outcome record into the telemetry store."""
    raise NotImplementedError


def persist_prompt(
    conn: duckdb.DuckDBPyConnection, session_id: str, prompt_text: str
) -> None:
    """Store a session prompt with truncation logic."""
    raise NotImplementedError


def get_session_prompt(
    conn: duckdb.DuckDBPyConnection, session_id: str
) -> PromptRecord | None:
    """Retrieve a session prompt record."""
    raise NotImplementedError


def record_scope_check(
    conn: duckdb.DuckDBPyConnection, result: ScopeCheckResult
) -> None:
    """Record a scope check result in the telemetry store."""
    raise NotImplementedError


def query_waste_report(
    conn: duckdb.DuckDBPyConnection, spec_number: int | None = None
) -> WasteReport:
    """Query aggregate waste report for no-op and pre-flight-skip sessions."""
    raise NotImplementedError
