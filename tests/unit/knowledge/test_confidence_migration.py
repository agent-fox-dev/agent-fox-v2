"""Tests for DuckDB confidence column migration.

Test Spec: TS-37-5, TS-37-6, TS-37-E3
Requirements: 37-REQ-2.1, 37-REQ-2.2, 37-REQ-2.3, 37-REQ-2.E1
"""

from __future__ import annotations

import uuid

import duckdb

from tests.unit.knowledge.conftest import create_schema


class TestConfidenceMigration:
    """TS-37-5, TS-37-6, TS-37-E3: DuckDB migration converts TEXT to FLOAT.

    Requirements: 37-REQ-2.1, 37-REQ-2.2, 37-REQ-2.3, 37-REQ-2.E1
    """

    def _make_pre_migration_db(self) -> duckdb.DuckDBPyConnection:
        """Create in-memory DuckDB with pre-migration schema."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        return conn

    def _insert_fact(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        fact_id: str | None = None,
        confidence: str | None = "high",
    ) -> str:
        """Insert a fact with given confidence, return the fact ID."""
        fid = fact_id or str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO memory_facts (id, content, category, spec_name,
                                      confidence, created_at)
            VALUES (?::UUID, 'test content', 'gotcha', 'test_spec',
                   ?, CURRENT_TIMESTAMP)
            """,
            [fid, confidence],
        )
        return fid

    def test_column_type_after_migration(self) -> None:
        """TS-37-5: After migration, confidence column is FLOAT."""
        conn = self._make_pre_migration_db()
        self._insert_fact(conn, confidence="high")
        self._insert_fact(conn, confidence="medium")
        self._insert_fact(conn, confidence="low")

        from agent_fox.knowledge.migrations import apply_pending_migrations

        apply_pending_migrations(conn)

        # Check column type
        cols = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'memory_facts' AND column_name = 'confidence'"
        ).fetchall()
        assert len(cols) == 1
        assert cols[0][1].upper() in ("FLOAT", "DOUBLE")

        conn.close()

    def test_value_conversion(self) -> None:
        """TS-37-5: String values are converted to canonical floats."""
        conn = self._make_pre_migration_db()
        self._insert_fact(conn, confidence="high")
        self._insert_fact(conn, confidence="medium")
        self._insert_fact(conn, confidence="low")

        from agent_fox.knowledge.migrations import apply_pending_migrations

        apply_pending_migrations(conn)

        rows = conn.execute("SELECT confidence FROM memory_facts").fetchall()
        values = {row[0] for row in rows}
        assert values == {0.9, 0.6, 0.3}
        for row in rows:
            assert isinstance(row[0], float)

        conn.close()

    def test_row_count_preserved(self) -> None:
        """TS-37-6: Migration preserves row count."""
        conn = self._make_pre_migration_db()
        for conf in ["high", "medium", "low", "high", "medium"]:
            self._insert_fact(conn, confidence=conf)

        count_before = conn.execute(
            "SELECT COUNT(*) FROM memory_facts"
        ).fetchone()[0]

        from agent_fox.knowledge.migrations import apply_pending_migrations

        apply_pending_migrations(conn)

        count_after = conn.execute(
            "SELECT COUNT(*) FROM memory_facts"
        ).fetchone()[0]
        assert count_before == count_after

        conn.close()

    def test_null_confidence_default(self) -> None:
        """TS-37-E3: NULL confidence rows get default 0.6 during migration."""
        conn = self._make_pre_migration_db()
        fid = self._insert_fact(conn, confidence=None)

        from agent_fox.knowledge.migrations import apply_pending_migrations

        apply_pending_migrations(conn)

        row = conn.execute(
            "SELECT confidence FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [fid],
        ).fetchone()
        assert row is not None
        assert row[0] == 0.6

        conn.close()
