"""Tests for entity signal activation via prior touched files.

Suite 3: Entity Signal Activation (TS-3.1 through TS-3.4)

Requirements: 113-REQ-3.1, 113-REQ-3.2, 113-REQ-3.E1
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest


@pytest.fixture
def knowledge_conn_with_schema():
    """In-memory DuckDB with full production schema."""
    from agent_fox.knowledge.migrations import run_migrations

    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


def _insert_session_outcome(
    conn: duckdb.DuckDBPyConnection,
    *,
    spec_name: str,
    status: str = "completed",
    touched_path: str | None = None,
    created_at: str | None = None,
) -> None:
    """Helper to insert a session outcome row."""
    row_id = str(uuid.uuid4())
    ts = created_at or datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO session_outcomes
            (id, spec_name, task_group, node_id, touched_path, status, created_at)
        VALUES (?::UUID, ?, '1', ?, ?, ?, ?::TIMESTAMP)
        """,
        [row_id, spec_name, f"{spec_name}:1", touched_path, status, ts],
    )


class TestSessionOutcomesTouchedPaths:
    """TS-3.1, TS-3.2, TS-3.3: Touched file data in session_outcomes.

    NOTE: Spec 114 (knowledge decoupling) removed _query_prior_touched_files
    from NodeSessionRunner. Retrieval of prior touched files is now delegated
    to the KnowledgeProvider protocol. These tests now verify that the
    session_outcomes data layer remains intact and queryable.
    """

    def test_touched_paths_stored_correctly(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-3.1: Session outcomes store and return touched paths."""

        conn = knowledge_conn_with_schema
        _insert_session_outcome(conn, spec_name="05_foo", touched_path="src/a.py,src/b.py")
        _insert_session_outcome(conn, spec_name="05_foo", touched_path="src/b.py,src/c.py")
        _insert_session_outcome(conn, spec_name="05_foo", touched_path=None)

        rows = conn.execute(
            "SELECT touched_path FROM session_outcomes "
            "WHERE spec_name = '05_foo' AND touched_path IS NOT NULL"
        ).fetchall()

        all_paths: set[str] = set()
        for (tp,) in rows:
            for p in tp.split(","):
                p = p.strip()
                if p:
                    all_paths.add(p)

        assert all_paths == {"src/a.py", "src/b.py", "src/c.py"}

    def test_null_touched_paths_excluded(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-3.1: Sessions with NULL touched_path are excluded from queries."""

        conn = knowledge_conn_with_schema
        _insert_session_outcome(conn, spec_name="05_foo", touched_path=None)
        _insert_session_outcome(conn, spec_name="05_foo", touched_path="src/real.py")

        rows = conn.execute(
            "SELECT touched_path FROM session_outcomes "
            "WHERE spec_name = '05_foo' AND touched_path IS NOT NULL"
        ).fetchall()

        paths = [tp for (tp,) in rows]
        assert "src/real.py" in paths

    def test_session_outcomes_support_many_paths(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-3.2: Session outcomes table supports storing many touched paths."""

        conn = knowledge_conn_with_schema
        base_time = datetime(2026, 1, 1, tzinfo=UTC)

        for i in range(60):
            ts = (base_time + timedelta(hours=i)).isoformat()
            _insert_session_outcome(
                conn,
                spec_name="05_foo",
                touched_path=f"src/file_{i:03d}.py",
                created_at=ts,
            )

        rows = conn.execute(
            "SELECT touched_path FROM session_outcomes "
            "WHERE spec_name = '05_foo' AND touched_path IS NOT NULL "
            "ORDER BY created_at DESC"
        ).fetchall()

        assert len(rows) == 60

    def test_recent_paths_ordered_by_timestamp(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-3.2: Paths are ordered by creation time (most recent first)."""

        conn = knowledge_conn_with_schema
        base_time = datetime(2026, 1, 1, tzinfo=UTC)

        for i in range(5):
            ts = (base_time + timedelta(hours=i)).isoformat()
            _insert_session_outcome(
                conn,
                spec_name="05_foo",
                touched_path=f"src/file_{i:03d}.py",
                created_at=ts,
            )

        rows = conn.execute(
            "SELECT touched_path FROM session_outcomes "
            "WHERE spec_name = '05_foo' AND touched_path IS NOT NULL "
            "ORDER BY created_at DESC"
        ).fetchall()

        paths = [tp for (tp,) in rows]
        assert paths[0] == "src/file_004.py"  # most recent
        assert paths[-1] == "src/file_000.py"  # oldest

    def test_empty_when_no_sessions(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-3.3: No rows returned when no prior sessions exist.

        Requirements: 113-REQ-3.E1
        """

        conn = knowledge_conn_with_schema
        rows = conn.execute(
            "SELECT touched_path FROM session_outcomes "
            "WHERE spec_name = '05_foo' AND touched_path IS NOT NULL"
        ).fetchall()

        assert rows == []


class TestBuildPromptsUsesKnowledgeProvider:
    """TS-3.4: Integration — _build_prompts calls KnowledgeProvider.retrieve().

    NOTE: Spec 114 (knowledge decoupling) replaced AdaptiveRetriever with
    the KnowledgeProvider protocol. _build_prompts now calls
    knowledge_provider.retrieve() instead of AdaptiveRetriever.retrieve().
    """

    def test_knowledge_provider_retrieve_called(
        self,
        tmp_path: Path,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-3.4: KnowledgeProvider.retrieve() is called during prompt assembly."""

        conn = knowledge_conn_with_schema
        _insert_session_outcome(conn, spec_name="05_foo", touched_path="src/main.py,src/utils.py")

        runner = _make_runner_with_conn(conn)
        runner._spec_name = "05_foo"
        runner._node_id = "05_foo:1"

        # Track whether retrieve was called
        retrieve_called = False
        original_retrieve = runner._knowledge_provider.retrieve

        def tracking_retrieve(spec_name, task_description, task_group=None, session_id=None):
            nonlocal retrieve_called
            retrieve_called = True
            return original_retrieve(spec_name, task_description, task_group=task_group, session_id=session_id)

        runner._knowledge_provider.retrieve = tracking_retrieve

        with (
            patch("agent_fox.engine.session_lifecycle.assemble_context", return_value=MagicMock()),
            patch("agent_fox.engine.session_lifecycle.build_system_prompt", return_value="sys"),
            patch("agent_fox.engine.session_lifecycle.build_task_prompt", return_value="task"),
            patch("agent_fox.core.config.resolve_spec_root", return_value=MagicMock()),
        ):
            runner._build_prompts(tmp_path, 1, None)

        assert retrieve_called, "KnowledgeProvider.retrieve() was never called"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_runner_with_conn(conn: duckdb.DuckDBPyConnection):
    """Create a NodeSessionRunner with the given DB connection."""
    from agent_fox.core.config import AgentFoxConfig
    from agent_fox.engine.session_lifecycle import NodeSessionRunner
    from agent_fox.knowledge.db import KnowledgeDB

    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = conn

    config = AgentFoxConfig()

    runner = NodeSessionRunner.__new__(NodeSessionRunner)
    runner._node_id = "05_foo:1"
    runner._spec_name = "05_foo"
    runner._run_id = "test-run"
    runner._config = config
    runner._knowledge_db = db
    runner._sink_dispatcher = None
    from agent_fox.knowledge.provider import NoOpKnowledgeProvider

    runner._knowledge_provider = NoOpKnowledgeProvider()
    runner._archetype = "coder"
    runner._mode = None
    runner._task_group = 2
    return runner
