"""Tests for learned blocking thresholds.

Test Spec: TS-39-29, TS-39-30, TS-39-31
Requirements: 39-REQ-10.1, 39-REQ-10.2, 39-REQ-10.3
"""

from __future__ import annotations

import duckdb
import pytest

from tests.unit.knowledge.conftest import create_schema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_blocking_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create blocking history and learned thresholds tables."""
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

        CREATE TABLE IF NOT EXISTS learned_thresholds (
            archetype VARCHAR PRIMARY KEY,
            threshold INTEGER NOT NULL,
            confidence FLOAT NOT NULL,
            sample_count INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT current_timestamp
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

    def test_record_decision(
        self, blocking_db: duckdb.DuckDBPyConnection
    ) -> None:
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

        rows = blocking_db.execute(
            "SELECT * FROM blocking_history"
        ).fetchall()
        assert len(rows) == 1
        # archetype is at index 2
        assert rows[0][2] == "skeptic"

    def test_compute_threshold(
        self, blocking_db: duckdb.DuckDBPyConnection
    ) -> None:
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

        threshold = compute_optimal_threshold(
            blocking_db, "skeptic", min_decisions=20
        )
        assert threshold is not None
        assert isinstance(threshold, int)
        assert threshold > 0

    def test_insufficient_decisions_returns_none(
        self, blocking_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Returns None when fewer than min_decisions exist."""
        from agent_fox.knowledge.blocking_history import compute_optimal_threshold

        threshold = compute_optimal_threshold(
            blocking_db, "skeptic", min_decisions=20
        )
        assert threshold is None

    def test_stored_thresholds(
        self, blocking_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-39-31: Learned thresholds stored in DuckDB.

        Requirement: 39-REQ-10.3
        """
        blocking_db.execute(
            """INSERT INTO learned_thresholds
               VALUES ('skeptic', 3, 0.85, 25, current_timestamp)"""
        )
        rows = blocking_db.execute(
            "SELECT * FROM learned_thresholds WHERE archetype='skeptic'"
        ).fetchall()
        assert len(rows) == 1
        # threshold is at index 1
        assert rows[0][1] == 3
