"""Property tests for review_store: supersession, migration idempotency.

Test Spec: TS-27-P1, TS-27-P6
Requirements: 27-REQ-1.2, 27-REQ-2.2, 27-REQ-4.1, 27-REQ-4.2
"""

from __future__ import annotations

import uuid

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.review_store import (
    ReviewFinding,
    insert_findings,
    query_active_findings,
)
from tests.unit.knowledge.conftest import create_schema


@st.composite
def review_finding_list(draw: st.DrawFn) -> list[ReviewFinding]:
    """Generate a list of ReviewFinding objects."""
    n = draw(st.integers(min_value=1, max_value=5))
    session_id = f"session-{draw(st.uuids())}"
    return [
        ReviewFinding(
            id=str(uuid.uuid4()),
            severity=draw(
                st.sampled_from(["critical", "major", "minor", "observation"])
            ),
            description=draw(st.text(min_size=1, max_size=100)),
            requirement_ref=draw(
                st.one_of(st.none(), st.text(min_size=1, max_size=20))
            ),
            spec_name="prop_test_spec",
            task_group="1",
            session_id=session_id,
        )
        for _ in range(n)
    ]


class TestSupersessionCompleteness:
    """TS-27-P1: Property 1 — Supersession Completeness.

    For any sequence of runs, only the latest has superseded_by IS NULL.
    """

    @given(
        batch1=review_finding_list(),
        batch2=review_finding_list(),
    )
    @settings(max_examples=20)
    def test_supersession_completeness(
        self,
        batch1: list[ReviewFinding],
        batch2: list[ReviewFinding],
    ) -> None:
        """Only the latest run's findings are active."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        insert_findings(conn, batch1)
        insert_findings(conn, batch2)

        active = query_active_findings(conn, "prop_test_spec")
        # All active findings should be from batch2's session
        session_ids = {f.session_id for f in active}
        assert len(session_ids) <= 1
        if session_ids:
            assert batch2[0].session_id in session_ids

        # batch1 should be superseded
        all_rows = conn.execute(
            "SELECT superseded_by FROM review_findings WHERE session_id = ?",
            [batch1[0].session_id],
        ).fetchall()
        for row in all_rows:
            assert row[0] is not None  # all superseded

        conn.close()


class TestMigrationIdempotency:
    """TS-27-P6: Property 6 — Migration Idempotency.

    Running migrations multiple times produces the same schema.
    """

    @given(n_runs=st.integers(min_value=1, max_value=5))
    @settings(max_examples=5)
    def test_migration_idempotency(self, n_runs: int) -> None:
        """Multiple migration runs produce same result."""
        from agent_fox.knowledge.migrations import apply_pending_migrations

        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            );
            INSERT INTO schema_version VALUES (1, CURRENT_TIMESTAMP, 'initial');
        """)
        # Also create fact_causes for the review_store to use
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fact_causes (
                cause_id UUID, effect_id UUID,
                PRIMARY KEY (cause_id, effect_id)
            );
        """)

        for _ in range(n_runs):
            apply_pending_migrations(conn)

        # Version should be 6 (latest migration: v6 audit_events)
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert version is not None
        assert version[0] == 6

        # Tables should exist (v2 + v3 + v4 migrations)
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN ("
            "  'review_findings', 'verification_results',"
            "  'complexity_assessments', 'execution_outcomes',"
            "  'drift_findings'"
            ") "
            "ORDER BY table_name"
        ).fetchall()
        assert len(tables) == 5

        conn.close()
