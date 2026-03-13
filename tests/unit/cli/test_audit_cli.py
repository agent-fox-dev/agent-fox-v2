"""Tests for the agent-fox audit CLI command.

Test Spec: TS-40-26 through TS-40-32
Requirements: 40-REQ-13.1, 40-REQ-13.2, 40-REQ-13.3, 40-REQ-13.4,
              40-REQ-13.5, 40-REQ-13.6, 40-REQ-13.7, 40-REQ-13.E1,
              40-REQ-13.E2
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import duckdb
import pytest
from agent_fox.cli.audit import audit_cmd
from click.testing import CliRunner


def _create_audit_db(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """Create the audit_events table for testing."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id          VARCHAR PRIMARY KEY,
            timestamp   TIMESTAMP NOT NULL,
            run_id      VARCHAR NOT NULL,
            event_type  VARCHAR NOT NULL,
            node_id     VARCHAR,
            session_id  VARCHAR,
            archetype   VARCHAR,
            severity    VARCHAR NOT NULL,
            payload     JSON NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_run_id
            ON audit_events (run_id);
        CREATE INDEX IF NOT EXISTS idx_audit_event_type
            ON audit_events (event_type);
    """)


def _insert_event(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str = "20260312_143000_abc123",
    event_type: str = "run.start",
    timestamp: datetime | None = None,
    node_id: str = "",
    severity: str = "info",
    payload: dict | None = None,
) -> str:
    """Insert a test event and return its ID."""
    event_id = str(uuid4())
    ts = timestamp or datetime.now(UTC)
    conn.execute(
        """
        INSERT INTO audit_events
            (id, timestamp, run_id, event_type, node_id, session_id,
             archetype, severity, payload)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            event_id,
            ts,
            run_id,
            event_type,
            node_id,
            "",
            "",
            severity,
            json.dumps(payload or {}),
        ],
    )
    return event_id


@pytest.fixture
def audit_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with audit_events table."""
    conn = duckdb.connect(":memory:")
    _create_audit_db(conn)
    yield conn  # type: ignore[misc]
    conn.close()


class TestAuditCLI:
    """TS-40-26 through TS-40-32: Audit CLI command.

    Requirements: 40-REQ-13.1 through 40-REQ-13.7, 40-REQ-13.E1, 40-REQ-13.E2
    """

    def test_list_runs(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-40-26: --list-runs shows available run IDs."""
        run1 = "20260312_100000_aaa111"
        run2 = "20260312_110000_bbb222"
        run3 = "20260312_120000_ccc333"
        for run_id in [run1, run2, run3]:
            _insert_event(audit_conn, run_id=run_id)
            _insert_event(audit_conn, run_id=run_id, event_type="run.complete")

        runner = CliRunner()
        with patch("agent_fox.cli.audit._get_audit_conn", return_value=audit_conn):
            result = runner.invoke(audit_cmd, ["--list-runs"])

        assert result.exit_code == 0
        assert "20260312" in result.output
        # Should show all 3 runs
        assert run1 in result.output
        assert run2 in result.output
        assert run3 in result.output

    def test_filter_by_run(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-40-27: --run filters to specific run ID."""
        run1 = "20260312_100000_aaa111"
        run2 = "20260312_110000_bbb222"
        _insert_event(audit_conn, run_id=run1)
        _insert_event(audit_conn, run_id=run2)

        runner = CliRunner()
        with patch("agent_fox.cli.audit._get_audit_conn", return_value=audit_conn):
            result = runner.invoke(audit_cmd, ["--run", run1])

        assert result.exit_code == 0
        assert run1 in result.output
        assert run2 not in result.output

    def test_filter_by_event_type(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-40-28: --event-type filters by event type."""
        _insert_event(audit_conn, event_type="session.complete")
        _insert_event(audit_conn, event_type="run.start")
        _insert_event(audit_conn, event_type="session.complete")

        runner = CliRunner()
        with patch("agent_fox.cli.audit._get_audit_conn", return_value=audit_conn):
            result = runner.invoke(audit_cmd, ["--event-type", "session.complete"])

        assert result.exit_code == 0
        assert "session.complete" in result.output

    def test_filter_by_node_id(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-40-27 (node-id variant): --node-id filters events."""
        _insert_event(audit_conn, node_id="spec_01/1")
        _insert_event(audit_conn, node_id="spec_02/2")

        runner = CliRunner()
        with patch("agent_fox.cli.audit._get_audit_conn", return_value=audit_conn):
            result = runner.invoke(audit_cmd, ["--node-id", "spec_01/1"])

        assert result.exit_code == 0
        assert "spec_01/1" in result.output

    def test_filter_by_since(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-40-29: --since 24h filters by time."""
        old_time = datetime.now(UTC) - timedelta(hours=48)
        recent_time = datetime.now(UTC) - timedelta(hours=1)

        _insert_event(
            audit_conn,
            run_id="old_run",
            timestamp=old_time,
            event_type="run.start",
        )
        _insert_event(
            audit_conn,
            run_id="recent_run",
            timestamp=recent_time,
            event_type="run.start",
        )

        runner = CliRunner()
        with patch("agent_fox.cli.audit._get_audit_conn", return_value=audit_conn):
            result = runner.invoke(audit_cmd, ["--since", "24h"])

        assert result.exit_code == 0
        assert "recent_run" in result.output
        assert "old_run" not in result.output

    def test_json_output(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-40-30: --json flag produces valid JSON output."""
        _insert_event(audit_conn)

        runner = CliRunner()
        with patch("agent_fox.cli.audit._get_audit_conn", return_value=audit_conn):
            result = runner.invoke(audit_cmd, ["--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, (list, dict))

    def test_no_events(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-40-31: No events returns exit code 0."""
        runner = CliRunner()
        with patch("agent_fox.cli.audit._get_audit_conn", return_value=audit_conn):
            result = runner.invoke(audit_cmd, [])

        assert result.exit_code == 0

    def test_missing_db(self) -> None:
        """TS-40-32: Missing DuckDB shows message and exits 0."""
        runner = CliRunner()
        with patch("agent_fox.cli.audit._get_audit_conn", return_value=None):
            result = runner.invoke(audit_cmd, [])

        assert result.exit_code == 0
        assert "no audit data" in result.output.lower()

    def test_since_iso_format(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """--since accepts ISO-8601 datetime."""
        recent = datetime.now(UTC) - timedelta(hours=1)
        _insert_event(audit_conn, timestamp=recent, run_id="recent")

        cutoff = (datetime.now(UTC) - timedelta(hours=2)).isoformat()

        runner = CliRunner()
        with patch("agent_fox.cli.audit._get_audit_conn", return_value=audit_conn):
            result = runner.invoke(audit_cmd, ["--since", cutoff])

        assert result.exit_code == 0
        assert "recent" in result.output

    def test_since_days(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """--since accepts relative durations like 7d."""
        recent = datetime.now(UTC) - timedelta(days=1)
        _insert_event(audit_conn, timestamp=recent, run_id="last_day")

        runner = CliRunner()
        with patch("agent_fox.cli.audit._get_audit_conn", return_value=audit_conn):
            result = runner.invoke(audit_cmd, ["--since", "7d"])

        assert result.exit_code == 0
        assert "last_day" in result.output
