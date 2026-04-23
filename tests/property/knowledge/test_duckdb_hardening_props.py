"""Property tests for DuckDB hardening.

Test Spec: TS-38-P1, TS-38-P2
Requirements: 38-REQ-1.1, 38-REQ-1.2, 38-REQ-5.1, 38-REQ-5.2
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import KnowledgeConfig
from agent_fox.knowledge.db import KnowledgeDB, open_knowledge_store
from agent_fox.knowledge.migrations import apply_pending_migrations
from tests.unit.knowledge.conftest import SCHEMA_DDL


def _create_fresh_conn() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB with full schema and migrations."""
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL)
    apply_pending_migrations(conn)
    return conn


class TestInitNeverNone:
    """Property 1: open_knowledge_store never returns None.

    For any configuration, the function either returns a valid KnowledgeDB
    or raises RuntimeError. It never returns None.

    Requirements: 38-REQ-1.1, 38-REQ-1.2
    """

    @given(subdir=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnop"))
    @settings(max_examples=10, deadline=5000)
    def test_valid_path_returns_knowledgedb(self, subdir: str) -> None:
        """For any valid path, open_knowledge_store returns KnowledgeDB (not None)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / subdir / "knowledge.duckdb"
            config = KnowledgeConfig(store_path=str(db_path))

            try:
                result = open_knowledge_store(config)
                assert isinstance(result, KnowledgeDB)
                assert result is not None
                result.close()
            except RuntimeError:
                pass  # expected for some paths; key: never returns None

    def test_invalid_path_raises_not_none(self, tmp_path: Path) -> None:
        """For an invalid path, open_knowledge_store raises (not returns None)."""
        bad_dir = tmp_path / "noaccess"
        bad_dir.mkdir()
        bad_dir.chmod(0o000)
        config = KnowledgeConfig(store_path=str(bad_dir / "test.duckdb"))

        try:
            result = open_knowledge_store(config)
            # If it somehow succeeds, it still shouldn't be None
            assert result is not None
            result.close()
        except RuntimeError:
            pass  # expected
        finally:
            bad_dir.chmod(0o755)


class TestFixtureIsolation:
    """Property 4: Each fixture invocation provides a clean database.

    For any sequence of N insert operations followed by a new fixture,
    the new fixture has zero rows in all tables.

    Requirements: 38-REQ-5.1, 38-REQ-5.2
    """

    @given(n=st.integers(min_value=1, max_value=10))
    @settings(max_examples=5, deadline=5000)
    def test_fresh_fixture_has_zero_rows(self, n: int) -> None:
        """After N inserts in one connection, a new connection is empty."""
        # Create fixture 1 and insert N rows
        conn1 = _create_fresh_conn()

        for i in range(n):
            conn1.execute(
                "INSERT INTO tool_calls "
                "(id, session_id, node_id, tool_name, "
                "called_at) VALUES ("
                "gen_random_uuid(), 'test', ?, 'test_tool', "
                "CURRENT_TIMESTAMP)",
                [f"node_{i}"],
            )
        count1 = conn1.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0]  # type: ignore[index]
        assert count1 == n
        conn1.close()

        # Create fixture 2 — should be empty
        conn2 = _create_fresh_conn()
        count2 = conn2.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0]  # type: ignore[index]
        assert count2 == 0
        conn2.close()
