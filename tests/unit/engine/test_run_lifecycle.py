"""Run lifecycle and stale run detection tests.

Test Spec: TS-118-13 (stale run detection on startup),
           TS-118-14 (cleanup handler transitions run on exit),
           TS-118-E7 (cleanup handler DB write failure),
           TS-118-E8 (multiple stale runs cleaned)
Requirements: 118-REQ-6.1, 118-REQ-6.2, 118-REQ-6.3,
              118-REQ-6.E1, 118-REQ-6.E2
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import duckdb
import pytest

from agent_fox.engine.state import cleanup_stale_runs


class TestStaleRunDetection:
    """TS-118-13: stale 'running' runs are detected and transitioned to 'stalled'.

    Requirements: 118-REQ-6.1

    NOTE: The spec requires status='stalled'. The existing cleanup_stale_runs()
    function uses status='interrupted'. Implementation must be updated to use
    'stalled' per the spec.
    """

    @pytest.fixture
    def runs_db(self) -> duckdb.DuckDBPyConnection:
        """Create an in-memory DuckDB with a runs table."""
        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id                  VARCHAR PRIMARY KEY,
                plan_content_hash   VARCHAR NOT NULL,
                started_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at        TIMESTAMP,
                status              VARCHAR NOT NULL DEFAULT 'running',
                total_input_tokens  BIGINT NOT NULL DEFAULT 0,
                total_output_tokens BIGINT NOT NULL DEFAULT 0,
                total_cost          DOUBLE NOT NULL DEFAULT 0.0,
                total_sessions      INTEGER NOT NULL DEFAULT 0
            )
        """)
        return conn

    def test_stale_run_detected_and_transitioned(
        self,
        runs_db: duckdb.DuckDBPyConnection,
    ) -> None:
        """Stale 'running' run from prior process is transitioned to 'stalled'."""
        # Insert a stale run (from prior process) and a completed run
        runs_db.execute(
            "INSERT INTO runs (id, plan_content_hash, status) VALUES (?, ?, ?)",
            ["stale_run", "hash1", "running"],
        )
        runs_db.execute(
            "INSERT INTO runs (id, plan_content_hash, status, completed_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["completed_run", "hash2", "completed"],
        )

        # cleanup_stale_runs transitions stale runs;
        # spec requires status='stalled' (not 'interrupted')
        stale_count = cleanup_stale_runs(runs_db, "current_run")

        assert stale_count == 1

        # The stale run should now be 'stalled'
        row = runs_db.execute(
            "SELECT status FROM runs WHERE id = ?", ["stale_run"]
        ).fetchone()
        assert row is not None
        assert row[0] == "stalled"

        # The completed run should be unchanged
        row2 = runs_db.execute(
            "SELECT status FROM runs WHERE id = ?", ["completed_run"]
        ).fetchone()
        assert row2 is not None
        assert row2[0] == "completed"


class TestCleanupHandler:
    """TS-118-14: cleanup handler transitions current run to 'stalled'.

    Requirements: 118-REQ-6.2, 118-REQ-6.3

    The spec requires registering an atexit/signal handler that wraps the
    DB transition and catches exceptions. This test verifies that a
    ``run_cleanup_handler`` function exists, transitions the run to 'stalled',
    and handles errors gracefully.
    """

    @pytest.fixture
    def runs_db(self) -> duckdb.DuckDBPyConnection:
        """Create an in-memory DuckDB with a runs table and a running run."""
        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id                  VARCHAR PRIMARY KEY,
                plan_content_hash   VARCHAR NOT NULL,
                started_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at        TIMESTAMP,
                status              VARCHAR NOT NULL DEFAULT 'running',
                total_input_tokens  BIGINT NOT NULL DEFAULT 0,
                total_output_tokens BIGINT NOT NULL DEFAULT 0,
                total_cost          DOUBLE NOT NULL DEFAULT 0.0,
                total_sessions      INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute(
            "INSERT INTO runs (id, plan_content_hash, status) VALUES (?, ?, ?)",
            ["test_run", "hash1", "running"],
        )
        return conn

    def test_cleanup_handler_transitions_to_stalled(
        self,
        runs_db: duckdb.DuckDBPyConnection,
    ) -> None:
        """When the cleanup handler is invoked, the current run transitions
        to 'stalled'.

        The spec requires a run_cleanup_handler() function that wraps
        complete_run() with exception handling. This test will fail until
        that wrapper is implemented."""
        # The cleanup handler wrapper should be importable
        from agent_fox.engine.state import run_cleanup_handler  # noqa: F811

        run_cleanup_handler("test_run", runs_db)

        row = runs_db.execute(
            "SELECT status FROM runs WHERE id = ?", ["test_run"]
        ).fetchone()
        assert row is not None
        assert row[0] == "stalled"


class TestCleanupHandlerDBFailure:
    """TS-118-E7: cleanup handler doesn't block on DB failure.

    Requirements: 118-REQ-6.E1
    """

    def test_cleanup_db_failure_no_raise(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Cleanup handler should not raise when DB write fails; it should
        log a WARNING and return gracefully.

        The spec requires run_cleanup_handler to catch DB exceptions.
        This test will fail until run_cleanup_handler is implemented."""
        from agent_fox.engine.state import run_cleanup_handler

        # Create a mock connection that raises on execute
        broken_conn = MagicMock()
        broken_conn.execute.side_effect = Exception("database locked")

        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.state"):
            # Must NOT raise — the handler must catch the exception
            run_cleanup_handler("test_run", broken_conn)

        # WARNING should have been logged
        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert len(warning_messages) > 0, (
            "run_cleanup_handler must log a WARNING when DB write fails"
        )


class TestMultipleStaleRunsCleaned:
    """TS-118-E8: all stale runs are cleaned on startup.

    Requirements: 118-REQ-6.E2
    """

    def test_all_stale_runs_transitioned(self) -> None:
        """When 3 stale runs exist, all should be transitioned to 'stalled'."""
        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id                  VARCHAR PRIMARY KEY,
                plan_content_hash   VARCHAR NOT NULL,
                started_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at        TIMESTAMP,
                status              VARCHAR NOT NULL DEFAULT 'running',
                total_input_tokens  BIGINT NOT NULL DEFAULT 0,
                total_output_tokens BIGINT NOT NULL DEFAULT 0,
                total_cost          DOUBLE NOT NULL DEFAULT 0.0,
                total_sessions      INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Insert 3 stale runs
        for rid in ["r1", "r2", "r3"]:
            conn.execute(
                "INSERT INTO runs (id, plan_content_hash, status) VALUES (?, ?, ?)",
                [rid, "hash", "running"],
            )

        count = cleanup_stale_runs(conn, "current_run")
        assert count == 3

        for rid in ["r1", "r2", "r3"]:
            row = conn.execute(
                "SELECT status FROM runs WHERE id = ?", [rid]
            ).fetchone()
            assert row is not None
            assert row[0] == "stalled"

        conn.close()
