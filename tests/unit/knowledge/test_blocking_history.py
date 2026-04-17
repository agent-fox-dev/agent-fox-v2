"""Tests for blocking history and threshold computation.

Test Spec: TS-39-29, TS-39-30,
           TS-43-11, TS-43-12, TS-43-13,
           TS-43-E7, TS-43-E8
Requirements: 39-REQ-10.1, 39-REQ-10.2,
              43-REQ-4.1, 43-REQ-4.2, 43-REQ-4.3,
              43-REQ-4.E1, 43-REQ-4.E2
"""

from __future__ import annotations

import duckdb
import pytest

from tests.unit.knowledge.conftest import create_schema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_blocking_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create blocking history table."""
    create_schema(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blocking_history (
            id VARCHAR PRIMARY KEY,
            spec_name VARCHAR NOT NULL,
            archetype VARCHAR NOT NULL,
            critical_count INTEGER NOT NULL,
            threshold INTEGER NOT NULL,
            blocked BOOLEAN NOT NULL,
            outcome VARCHAR,
            created_at TIMESTAMP DEFAULT current_timestamp
        );
    """)


@pytest.fixture
def blocking_db() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with blocking history schema."""
    conn = duckdb.connect(":memory:")
    _create_blocking_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# TS-39-29: Blocking Decision Recording
# ---------------------------------------------------------------------------


class TestBlockingHistory:
    """TS-39-29, TS-39-30, TS-39-31: Blocking history and thresholds.

    Requirements: 39-REQ-10.1, 39-REQ-10.2, 39-REQ-10.3
    """

    def test_record_decision(self, blocking_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-29: Blocking decisions are tracked.

        Requirement: 39-REQ-10.1
        """
        from agent_fox.knowledge.blocking_history import (
            BlockingDecision,
            record_blocking_decision,
        )

        decision = BlockingDecision(
            spec_name="foo",
            archetype="skeptic",
            critical_count=3,
            threshold=2,
            blocked=True,
            outcome="correct_block",
        )
        record_blocking_decision(blocking_db, decision)

        rows = blocking_db.execute("SELECT * FROM blocking_history").fetchall()
        assert len(rows) == 1
        # archetype is at index 2
        assert rows[0][2] == "skeptic"

    def test_compute_threshold(self, blocking_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-30: Optimal threshold computed from blocking history.

        Requirement: 39-REQ-10.2
        """
        from agent_fox.knowledge.blocking_history import (
            BlockingDecision,
            compute_optimal_threshold,
            record_blocking_decision,
        )

        # Insert 25 mixed blocking decisions
        for i in range(25):
            critical_count = i % 5 + 1
            threshold = 3
            blocked = critical_count > threshold
            # Simulate outcomes
            if blocked and critical_count > 3:
                outcome = "correct_block"
            elif blocked:
                outcome = "false_positive"
            elif critical_count > 3:
                outcome = "missed_block"
            else:
                outcome = "correct_pass"

            decision = BlockingDecision(
                spec_name=f"spec_{i}",
                archetype="skeptic",
                critical_count=critical_count,
                threshold=threshold,
                blocked=blocked,
                outcome=outcome,
            )
            record_blocking_decision(blocking_db, decision)

        optimal = compute_optimal_threshold(blocking_db, "skeptic", min_decisions=20)
        assert optimal is not None
        assert isinstance(optimal, int)
        assert optimal > 0

    def test_insufficient_decisions_returns_none(self, blocking_db: duckdb.DuckDBPyConnection) -> None:
        """Returns None when fewer than min_decisions exist."""
        from agent_fox.knowledge.blocking_history import compute_optimal_threshold

        optimal = compute_optimal_threshold(blocking_db, "skeptic", min_decisions=20)
        assert optimal is None



# ---------------------------------------------------------------------------
# Spec 43: Blocking History tests
# ---------------------------------------------------------------------------


class TestRecordBlockingDecision:
    """TS-43-11: Record blocking decision.

    Requirement: 43-REQ-4.1
    """

    def test_record(self, blocking_db: duckdb.DuckDBPyConnection) -> None:
        """TS-43-11: Blocking decisions persisted to DuckDB.

        Requirement: 43-REQ-4.1
        """
        from agent_fox.knowledge.blocking_history import (
            BlockingDecision,
            record_blocking_decision,
        )

        decision = BlockingDecision("spec_a", "skeptic", 3, 2, True, "correct_block")
        record_blocking_decision(blocking_db, decision)

        rows = blocking_db.execute("SELECT * FROM blocking_history").fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "spec_a"  # spec_name
        assert rows[0][2] == "skeptic"  # archetype


class TestComputeOptimalThreshold:
    """TS-43-12, TS-43-13: Compute optimal threshold.

    Requirements: 43-REQ-4.2, 43-REQ-4.3
    """

    def test_sufficient_data(self, blocking_db: duckdb.DuckDBPyConnection) -> None:
        """TS-43-12: Optimal threshold with sufficient data.

        Requirement: 43-REQ-4.2

        Preconditions: 25 blocking decisions for "skeptic":
        - 15 correct_block with critical_count 3-5
        - 5 correct_pass with critical_count 0-1
        - 5 false_positive with critical_count 2
        """
        from agent_fox.knowledge.blocking_history import (
            BlockingDecision,
            compute_optimal_threshold,
            record_blocking_decision,
        )

        # 15 correct_block with critical_count 3-5
        for i in range(15):
            cc = 3 + (i % 3)  # 3, 4, 5, 3, 4, 5, ...
            record_blocking_decision(
                blocking_db,
                BlockingDecision(f"s{i}", "skeptic", cc, 2, True, "correct_block"),
            )

        # 5 correct_pass with critical_count 0-1
        for i in range(5):
            cc = i % 2  # 0, 1, 0, 1, 0
            record_blocking_decision(
                blocking_db,
                BlockingDecision(f"p{i}", "skeptic", cc, 2, False, "correct_pass"),
            )

        # 5 false_positive with critical_count 2
        for i in range(5):
            record_blocking_decision(
                blocking_db,
                BlockingDecision(f"fp{i}", "skeptic", 2, 2, True, "false_positive"),
            )

        threshold = compute_optimal_threshold(blocking_db, "skeptic", min_decisions=20)
        assert threshold is not None
        assert isinstance(threshold, int)
        assert threshold >= 1

    def test_insufficient_data(self, blocking_db: duckdb.DuckDBPyConnection) -> None:
        """TS-43-13: None returned when insufficient decisions exist.

        Requirement: 43-REQ-4.3

        Preconditions: 5 blocking decisions (below min_decisions=20).
        """
        from agent_fox.knowledge.blocking_history import (
            BlockingDecision,
            compute_optimal_threshold,
            record_blocking_decision,
        )

        for i in range(5):
            record_blocking_decision(
                blocking_db,
                BlockingDecision(f"s{i}", "skeptic", 3, 2, True, "correct_block"),
            )

        threshold = compute_optimal_threshold(blocking_db, "skeptic", min_decisions=20)
        assert threshold is None


class TestBlockingEdgeCases:
    """TS-43-E7, TS-43-E8: Blocking edge cases.

    Requirements: 43-REQ-4.E1, 43-REQ-4.E2
    """

    def test_missing_table(self) -> None:
        """TS-43-E7: compute_optimal_threshold handles missing table.

        Requirement: 43-REQ-4.E1

        Preconditions: DuckDB connection without blocking_history table.
        """
        import duckdb as ddb

        from agent_fox.knowledge.blocking_history import compute_optimal_threshold

        conn = ddb.connect(":memory:")
        threshold = compute_optimal_threshold(conn, "skeptic")
        assert threshold is None

    def test_uniform_outcomes(self, blocking_db: duckdb.DuckDBPyConnection) -> None:
        """TS-43-E8: Threshold with all-same-outcome history.

        Requirement: 43-REQ-4.E2

        Preconditions: 25 decisions all with outcome "correct_pass".
        """
        from agent_fox.knowledge.blocking_history import (
            BlockingDecision,
            compute_optimal_threshold,
            record_blocking_decision,
        )

        for i in range(25):
            record_blocking_decision(
                blocking_db,
                BlockingDecision(f"s{i}", "skeptic", i % 3, 5, False, "correct_pass"),
            )

        threshold = compute_optimal_threshold(blocking_db, "skeptic", min_decisions=20)
        assert threshold is not None
        assert isinstance(threshold, int)


# ---------------------------------------------------------------------------
# Regression: migration v13 creates the tables in production schema
# ---------------------------------------------------------------------------


class TestMigrationCreatesBlockingHistory:
    """Regression for issue #449: blocking_history table missing in production.

    Verifies that run_migrations() creates blocking_history so that
    record_blocking_decision() does not raise CatalogException.
    """

    def test_run_migrations_creates_blocking_history(self) -> None:
        """Regression #449: run_migrations creates blocking_history table."""
        import duckdb as ddb

        from agent_fox.knowledge.blocking_history import (
            BlockingDecision,
            record_blocking_decision,
        )
        from agent_fox.knowledge.migrations import run_migrations

        conn = ddb.connect(":memory:")
        run_migrations(conn)

        decision = BlockingDecision(
            spec_name="regression_449",
            archetype="skeptic",
            critical_count=2,
            threshold=3,
            blocked=False,
            outcome="correct_pass",
        )
        record_blocking_decision(conn, decision)

        rows = conn.execute("SELECT spec_name FROM blocking_history").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "regression_449"
