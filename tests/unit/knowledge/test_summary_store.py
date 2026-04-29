"""Unit tests for summary_store: insert, schema, queries, and edge cases.

Test Spec: TS-119-1, TS-119-2, TS-119-3, TS-119-4, TS-119-5, TS-119-7,
           TS-119-8, TS-119-9, TS-119-10, TS-119-11, TS-119-13, TS-119-14,
           TS-119-15,
           TS-119-E1, TS-119-E2, TS-119-E3, TS-119-E4, TS-119-E5, TS-119-E6,
           TS-119-E7, TS-119-E8, TS-119-E9
Requirements: 119-REQ-1.1 through 119-REQ-1.4,
              119-REQ-2.1 through 119-REQ-2.6,
              119-REQ-3.1 through 119-REQ-3.5,
              119-REQ-1.E1 through 119-REQ-1.E3,
              119-REQ-2.E1 through 119-REQ-2.E3,
              119-REQ-3.E1, 119-REQ-3.E2,
              119-REQ-4.E1, 119-REQ-5.E1
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import duckdb
import pytest

from agent_fox.knowledge.migrations import run_migrations
from agent_fox.knowledge.summary_store import (
    SummaryRecord,
    insert_summary,
    query_cross_spec_summaries,
    query_same_spec_summaries,
    truncate_for_audit,
)

_SESSION_SUMMARIES_DDL = """
CREATE TABLE IF NOT EXISTS session_summaries (
    id          UUID PRIMARY KEY,
    node_id     VARCHAR NOT NULL,
    run_id      VARCHAR NOT NULL,
    spec_name   VARCHAR NOT NULL,
    task_group  VARCHAR NOT NULL,
    archetype   VARCHAR NOT NULL,
    attempt     INTEGER NOT NULL DEFAULT 1,
    summary     TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL
);
"""


@pytest.fixture()
def summary_conn():
    """In-memory DuckDB with full schema + session_summaries table."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    conn.execute(_SESSION_SUMMARIES_DDL)
    yield conn
    conn.close()


def _make_record(
    *,
    id: str | None = None,
    node_id: str = "spec_a:3",
    run_id: str = "run-1",
    spec_name: str = "spec_a",
    task_group: str = "3",
    archetype: str = "coder",
    attempt: int = 1,
    summary: str = "Implemented the store",
    created_at: str = "2026-04-28T18:00:00",
) -> SummaryRecord:
    return SummaryRecord(
        id=id or str(uuid.uuid4()),
        node_id=node_id,
        run_id=run_id,
        spec_name=spec_name,
        task_group=task_group,
        archetype=archetype,
        attempt=attempt,
        summary=summary,
        created_at=created_at,
    )


# TS-119-1: Insert summary stores correct row (119-REQ-1.1)
class TestInsertSummaryStoresCorrectRow:
    def test_insert_stores_all_fields(self, summary_conn):
        record = _make_record(
            id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            node_id="spec_a:3", run_id="run-1", spec_name="spec_a",
            task_group="3", archetype="coder", attempt=1,
            summary="Implemented SQLite store",
            created_at="2026-04-28T18:00:00",
        )
        insert_summary(summary_conn, record)
        rows = summary_conn.execute("SELECT * FROM session_summaries").fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert str(row[1]) == "spec_a:3"
        assert str(row[7]) == "Implemented SQLite store"
        assert str(row[5]) == "coder"
        assert row[6] == 1


# TS-119-2: Table schema matches specification (119-REQ-1.2)
class TestTableSchemaMatchesSpec:
    def test_table_has_correct_columns(self, summary_conn):
        cols = summary_conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'session_summaries'"
        ).fetchall()
        col_map = {c[0]: c[1] for c in cols}
        assert "id" in col_map
        assert "node_id" in col_map
        assert "run_id" in col_map
        assert "spec_name" in col_map
        assert "task_group" in col_map
        assert "archetype" in col_map
        assert "attempt" in col_map
        assert "summary" in col_map
        assert "created_at" in col_map
        assert len(col_map) == 9


# TS-119-3: Append-only retains all attempts (119-REQ-1.3)
class TestAppendOnlyRetainsAllAttempts:
    def test_two_attempts_both_stored(self, summary_conn):
        r1 = _make_record(id=str(uuid.uuid4()), node_id="spec_a:3", attempt=1, summary="First try")
        r2 = _make_record(id=str(uuid.uuid4()), node_id="spec_a:3", attempt=2, summary="Fixed issues")
        insert_summary(summary_conn, r1)
        insert_summary(summary_conn, r2)
        rows = summary_conn.execute(
            "SELECT attempt, summary FROM session_summaries WHERE node_id = 'spec_a:3'"
        ).fetchall()
        assert len(rows) == 2
        summaries = {r[0]: r[1] for r in rows}
        assert summaries[1] == "First try"
        assert summaries[2] == "Fixed issues"


# TS-119-4: Migration v24 creates table (119-REQ-1.4)
class TestMigrationV24CreatesTable:
    def test_migration_creates_table(self):
        conn = duckdb.connect(":memory:")
        try:
            run_migrations(conn)
            version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
            assert version >= 24
            conn.execute(
                "INSERT INTO session_summaries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [str(uuid.uuid4()), "spec_a:1", "run-1", "spec_a", "1", "coder", 1, "test", "2026-04-28T18:00:00"],
            )
            count = conn.execute("SELECT COUNT(*) FROM session_summaries").fetchone()[0]
            assert count == 1
        finally:
            conn.close()


# TS-119-5: Same-spec retrieval returns prior groups only (119-REQ-2.1)
class TestSameSpecReturnsPriorGroupsOnly:
    def test_returns_prior_groups(self, summary_conn):
        for g in [1, 2, 3, 4]:
            insert_summary(summary_conn, _make_record(
                id=str(uuid.uuid4()), task_group=str(g), node_id=f"spec_a:{g}", summary=f"Group {g}",
            ))
        results = query_same_spec_summaries(summary_conn, "spec_a", "3", "run-1")
        groups = [r.task_group for r in results]
        assert groups == ["1", "2"]


# TS-119-7: Latest attempt only in retrieval (119-REQ-2.3)
class TestLatestAttemptOnlyInRetrieval:
    def test_latest_attempt_returned(self, summary_conn):
        insert_summary(summary_conn, _make_record(
            id=str(uuid.uuid4()), task_group="2", node_id="spec_a:2", attempt=1, summary="First",
        ))
        insert_summary(summary_conn, _make_record(
            id=str(uuid.uuid4()), task_group="2", node_id="spec_a:2", attempt=2, summary="Fixed",
        ))
        results = query_same_spec_summaries(summary_conn, "spec_a", "3", "run-1")
        assert len(results) == 1
        assert results[0].attempt == 2
        assert results[0].summary == "Fixed"


# TS-119-8: Sort order is task group ascending (119-REQ-2.4)
class TestSortOrderTaskGroupAscending:
    def test_sorted_ascending(self, summary_conn):
        for g in [1, 3, 2]:
            insert_summary(summary_conn, _make_record(
                id=str(uuid.uuid4()), task_group=str(g), node_id=f"spec_a:{g}",
            ))
        results = query_same_spec_summaries(summary_conn, "spec_a", "5", "run-1")
        groups = [r.task_group for r in results]
        assert groups == ["1", "2", "3"]


# TS-119-9: Same-spec cap applied (119-REQ-2.5)
class TestSameSpecCapApplied:
    def test_cap_at_five(self, summary_conn):
        for g in range(1, 9):
            insert_summary(summary_conn, _make_record(
                id=str(uuid.uuid4()), task_group=str(g), node_id=f"spec_a:{g}",
            ))
        results = query_same_spec_summaries(summary_conn, "spec_a", "9", "run-1", max_items=5)
        assert len(results) == 5


# TS-119-10: Only coder summaries retrieved (119-REQ-2.6)
class TestAllArchetypeSummariesRetrieved:
    """120-REQ-3.3: query returns summaries from all archetypes, not just coder."""

    def test_includes_all_archetypes(self, summary_conn):
        for arch in ["coder", "reviewer", "verifier"]:
            insert_summary(summary_conn, _make_record(
                id=str(uuid.uuid4()), task_group="2", node_id=f"spec_a:2:{arch}", archetype=arch,
            ))
        results = query_same_spec_summaries(summary_conn, "spec_a", "3", "run-1")
        assert len(results) == 3
        archetypes = {r.archetype for r in results}
        assert archetypes == {"coder", "reviewer", "verifier"}


# TS-119-11: Cross-spec retrieval excludes current spec (119-REQ-3.1)
class TestCrossSpecExcludesCurrentSpec:
    def test_excludes_own_spec(self, summary_conn):
        insert_summary(summary_conn, _make_record(
            id=str(uuid.uuid4()), spec_name="spec_a", task_group="2", node_id="spec_a:2",
        ))
        insert_summary(summary_conn, _make_record(
            id=str(uuid.uuid4()), spec_name="spec_b", task_group="3", node_id="spec_b:3",
        ))
        results = query_cross_spec_summaries(summary_conn, "spec_a", "run-1")
        assert len(results) == 1
        assert results[0].spec_name == "spec_b"


# TS-119-13: Cross-spec cap applied (119-REQ-3.3)
class TestCrossSpecCapApplied:
    def test_cap_at_three(self, summary_conn):
        for s in ["spec_b", "spec_c", "spec_d", "spec_e", "spec_f"]:
            insert_summary(summary_conn, _make_record(
                id=str(uuid.uuid4()), spec_name=s, task_group="1", node_id=f"{s}:1",
            ))
        results = query_cross_spec_summaries(summary_conn, "spec_a", "run-1", max_items=3)
        assert len(results) == 3


# TS-119-14: Cross-spec sorted by created_at descending (119-REQ-3.4)
class TestCrossSpecSortedCreatedAtDesc:
    def test_most_recent_first(self, summary_conn):
        insert_summary(summary_conn, _make_record(
            id=str(uuid.uuid4()), spec_name="spec_b", task_group="1",
            node_id="spec_b:1", created_at="2026-04-28T10:00:00",
        ))
        insert_summary(summary_conn, _make_record(
            id=str(uuid.uuid4()), spec_name="spec_c", task_group="1",
            node_id="spec_c:1", created_at="2026-04-28T11:00:00",
        ))
        results = query_cross_spec_summaries(summary_conn, "spec_a", "run-1")
        assert results[0].spec_name == "spec_c"
        assert results[1].spec_name == "spec_b"


# TS-119-15: Cross-spec latest attempt only (119-REQ-3.5)
class TestCrossSpecLatestAttemptOnly:
    def test_latest_attempt_per_spec_group(self, summary_conn):
        insert_summary(summary_conn, _make_record(
            id=str(uuid.uuid4()), spec_name="spec_b", task_group="2", node_id="spec_b:2",
            attempt=1, summary="First attempt", created_at="2026-04-28T10:00:00",
        ))
        insert_summary(summary_conn, _make_record(
            id=str(uuid.uuid4()), spec_name="spec_b", task_group="2", node_id="spec_b:2",
            attempt=2, summary="Second attempt", created_at="2026-04-28T11:00:00",
        ))
        results = query_cross_spec_summaries(summary_conn, "spec_a", "run-1")
        assert len(results) == 1
        assert results[0].attempt == 2


# TS-119-E1: Missing summary artifact (119-REQ-1.E1)
class TestMissingSummaryArtifact:
    def test_read_artifacts_returns_none_for_missing_file(self, tmp_path):
        from agent_fox.engine.session_lifecycle import NodeSessionRunner
        workspace = MagicMock()
        workspace.path = tmp_path
        result = NodeSessionRunner._read_session_artifacts(workspace)
        assert result is None


# TS-119-E2: Failed session skips summary (119-REQ-1.E2)
class TestFailedSessionSkipsSummary:
    def test_ingest_skips_on_failed_status(self, summary_conn):
        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.db import KnowledgeDB
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        db = KnowledgeDB.__new__(KnowledgeDB)
        db._conn = summary_conn
        provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())

        # Precondition: verify that a completed session DOES store a summary.
        # This fails until ingest() handles summaries, preventing the
        # negative test below from passing trivially.
        provider.ingest("spec_a:2", "spec_a", {
            "summary": "Completed work", "session_status": "completed",
            "touched_files": [], "commit_sha": "abc",
            "archetype": "coder", "task_group": "2", "attempt": 1,
        })
        completed_count = summary_conn.execute(
            "SELECT COUNT(*) FROM session_summaries"
        ).fetchone()[0]
        assert completed_count == 1  # Fails until implementation exists

        # Actual test: a failed session must NOT store a summary row.
        provider.ingest("spec_a:3", "spec_a", {
            "summary": "Some text", "session_status": "failed",
            "touched_files": [], "commit_sha": "",
            "archetype": "coder", "task_group": "3", "attempt": 1,
        })
        total_count = summary_conn.execute(
            "SELECT COUNT(*) FROM session_summaries"
        ).fetchone()[0]
        assert total_count == 1  # Still 1 — failed session didn't add a row


# TS-119-E3: Missing table handled gracefully (119-REQ-1.E3, 119-REQ-2.E3)
class TestMissingTableHandledGracefully:
    def test_same_spec_returns_empty(self):
        conn = duckdb.connect(":memory:")
        try:
            results = query_same_spec_summaries(conn, "spec_a", "3", "run-1")
            assert results == []
        finally:
            conn.close()

    def test_cross_spec_returns_empty(self):
        conn = duckdb.connect(":memory:")
        try:
            results = query_cross_spec_summaries(conn, "spec_a", "run-1")
            assert results == []
        finally:
            conn.close()


# TS-119-E4: Task group 1 returns empty (119-REQ-2.E1)
class TestTaskGroup1ReturnsEmpty:
    def test_group_1_empty(self, summary_conn):
        for g in [1, 2, 3]:
            insert_summary(summary_conn, _make_record(
                id=str(uuid.uuid4()), task_group=str(g), node_id=f"spec_a:{g}",
            ))
        results = query_same_spec_summaries(summary_conn, "spec_a", "1", "run-1")
        assert results == []


# TS-119-E5: Non-coder prior groups now included (120-REQ-3.3 supersedes 119-REQ-2.E2)
class TestNonCoderPriorGroupsIncluded:
    """120-REQ-3.3: all archetypes are now returned, not just coder."""

    def test_non_coder_prior_groups_returned(self, summary_conn):
        insert_summary(summary_conn, _make_record(
            id=str(uuid.uuid4()), task_group="1", node_id="spec_a:1:reviewer", archetype="reviewer",
        ))
        insert_summary(summary_conn, _make_record(
            id=str(uuid.uuid4()), task_group="2", node_id="spec_a:2:verifier", archetype="verifier",
        ))
        results = query_same_spec_summaries(summary_conn, "spec_a", "3", "run-1")
        assert len(results) == 2
        archetypes = {r.archetype for r in results}
        assert archetypes == {"reviewer", "verifier"}


# TS-119-E6: No cross-spec summaries in run (119-REQ-3.E1)
class TestNoCrossSpecSummariesInRun:
    def test_only_own_spec(self, summary_conn):
        insert_summary(summary_conn, _make_record(
            id=str(uuid.uuid4()), spec_name="spec_a", node_id="spec_a:1",
        ))
        results = query_cross_spec_summaries(summary_conn, "spec_a", "run-1")
        assert results == []


# TS-119-E7: No run_id skips cross-spec (119-REQ-3.E2)
class TestNoRunIdSkipsCrossSpec:
    def test_no_run_id_no_cross_spec(self, summary_conn):
        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.db import KnowledgeDB
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
        insert_summary(summary_conn, _make_record(
            id=str(uuid.uuid4()), spec_name="spec_b", task_group="1", node_id="spec_b:1",
        ))
        db = KnowledgeDB.__new__(KnowledgeDB)
        db._conn = summary_conn
        provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())
        items = provider.retrieve("spec_a", "desc", task_group="2")
        cross_items = [i for i in items if i.startswith("[CROSS-SPEC]")]
        assert cross_items == []


# TS-119-E8: Audit summary truncated at 2000 chars (119-REQ-4.E1)
class TestAuditSummaryTruncated:
    def test_truncation_at_2000(self):
        long_summary = "x" * 3000
        truncated = truncate_for_audit(long_summary)
        assert len(truncated) == 2003
        assert truncated.endswith("...")
        # Original text is unchanged
        assert len(long_summary) == 3000

    def test_no_truncation_under_limit(self):
        short_summary = "x" * 500
        result = truncate_for_audit(short_summary)
        assert result == short_summary
        assert len(result) == 500


# TS-119-E9: DB failure during insert does not crash (119-REQ-5.E1)
class TestDbFailureDoesNotCrash:
    def test_broken_conn_no_crash(self, caplog):
        import logging

        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.db import KnowledgeDB
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        broken_conn = MagicMock()
        broken_conn.execute.side_effect = RuntimeError("DB is closed")
        broken_db = KnowledgeDB.__new__(KnowledgeDB)
        broken_db._conn = broken_conn
        provider_broken = FoxKnowledgeProvider(broken_db, KnowledgeProviderConfig())

        # Should not raise
        with caplog.at_level(logging.WARNING):
            provider_broken.ingest("spec_a:3", "spec_a", {
                "summary": "text", "session_status": "completed",
                "touched_files": [], "commit_sha": "",
                "archetype": "coder", "task_group": "3", "attempt": 1,
            })

        # After implementation, a warning about summary insertion failure
        # should be logged. This assertion fails until ingest() handles
        # summaries and logs graceful DB errors.
        assert any(
            "summary" in r.message.lower()
            for r in caplog.records
            if r.levelno >= logging.WARNING
        )
