"""Tests for audit log retention logic.

Test Spec: TS-40-24, TS-40-25, TS-40-E2
Requirements: 40-REQ-12.1, 40-REQ-12.2, 40-REQ-12.E1, 40-REQ-12.E2
"""

from __future__ import annotations

import json
import logging
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from agent_fox.knowledge.audit import (
    enforce_audit_retention,
)


def _insert_run_events(
    conn: duckdb.DuckDBPyConnection,
    audit_dir: Path,
    run_id: str,
    timestamp: datetime,
    event_count: int = 2,
) -> None:
    """Helper: insert events for a run into DuckDB and create JSONL file."""
    from uuid import uuid4

    for i in range(event_count):
        ts = timestamp + timedelta(seconds=i)
        conn.execute(
            """
            INSERT INTO audit_events
                (id, timestamp, run_id, event_type, node_id, session_id,
                 archetype, severity, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid4()),
                ts,
                run_id,
                "run.start" if i == 0 else "run.complete",
                "",
                "",
                "",
                "info",
                json.dumps({}),
            ],
        )

    # Create corresponding JSONL file
    jsonl_path = audit_dir / f"audit_{run_id}.jsonl"
    with open(jsonl_path, "w") as f:
        f.write(json.dumps({"run_id": run_id, "event_type": "run.start"}) + "\n")


class TestRetention:
    """TS-40-24, TS-40-25, TS-40-E2: Audit log retention.

    Requirements: 40-REQ-12.1, 40-REQ-12.2, 40-REQ-12.E1, 40-REQ-12.E2
    """

    def test_deletes_old(self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """TS-40-24: Retention deletes oldest runs beyond limit."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir(parents=True)

        base_time = datetime(2026, 1, 1, tzinfo=UTC)
        # Create 25 runs
        for i in range(25):
            run_id = f"20260101_{i:06d}_abc{i:03d}"
            _insert_run_events(knowledge_conn, audit_dir, run_id, base_time + timedelta(hours=i))

        enforce_audit_retention(audit_dir, knowledge_conn, max_runs=20)

        remaining = knowledge_conn.execute("SELECT DISTINCT run_id FROM audit_events").fetchall()
        assert len(remaining) == 20

        jsonl_files = list(audit_dir.glob("audit_*.jsonl"))
        assert len(jsonl_files) == 20

    def test_under_limit(self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """TS-40-25: No data deleted when under retention limit."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir(parents=True)

        base_time = datetime(2026, 1, 1, tzinfo=UTC)
        for i in range(10):
            run_id = f"20260101_{i:06d}_abc{i:03d}"
            _insert_run_events(knowledge_conn, audit_dir, run_id, base_time + timedelta(hours=i))

        enforce_audit_retention(audit_dir, knowledge_conn, max_runs=20)

        remaining = knowledge_conn.execute("SELECT DISTINCT run_id FROM audit_events").fetchall()
        assert len(remaining) == 10

    def test_jsonl_delete_failure(
        self,
        knowledge_conn: duckdb.DuckDBPyConnection,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """TS-40-E2: JSONL deletion failure logs warning and continues."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir(parents=True)

        base_time = datetime(2026, 1, 1, tzinfo=UTC)
        # Create 3 runs, retain 1
        for i in range(3):
            run_id = f"20260101_{i:06d}_abc{i:03d}"
            _insert_run_events(knowledge_conn, audit_dir, run_id, base_time + timedelta(hours=i))

        # Make the oldest JSONL file read-only (undeletable)
        oldest_file = audit_dir / "audit_20260101_000000_abc000.jsonl"
        if oldest_file.exists():
            # Make directory read-only to prevent deletion on some OS
            oldest_file.chmod(stat.S_IRUSR)

        with caplog.at_level(logging.WARNING):
            enforce_audit_retention(audit_dir, knowledge_conn, max_runs=1)

        # DuckDB cleanup should still have happened
        remaining = knowledge_conn.execute("SELECT DISTINCT run_id FROM audit_events").fetchall()
        assert len(remaining) == 1

        # Restore permissions for cleanup
        if oldest_file.exists():
            oldest_file.chmod(stat.S_IRWXU)

    def test_empty_database(self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Retention with no events is a no-op."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir(parents=True)

        enforce_audit_retention(audit_dir, knowledge_conn, max_runs=20)

        remaining = knowledge_conn.execute("SELECT DISTINCT run_id FROM audit_events").fetchall()
        assert len(remaining) == 0
