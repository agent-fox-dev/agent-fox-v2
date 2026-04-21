"""Tests for entity signal activation via prior touched files.

Suite 3: Entity Signal Activation (TS-3.1 through TS-3.4)

Requirements: 113-REQ-3.1, 113-REQ-3.2, 113-REQ-3.E1
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

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


class TestQueryPriorTouchedFiles:
    """TS-3.1, TS-3.2, TS-3.3: _query_prior_touched_files unit tests."""

    def test_returns_deduplicated_paths(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-3.1: Returns deduplicated list of touched paths from prior sessions."""

        conn = knowledge_conn_with_schema
        # Session 1: touches a.py and b.py (comma-delimited)
        _insert_session_outcome(conn, spec_name="05_foo", touched_path="src/a.py,src/b.py")
        # Session 2: touches b.py and c.py (b.py is duplicated)
        _insert_session_outcome(conn, spec_name="05_foo", touched_path="src/b.py,src/c.py")
        # Session 3: NULL touched_path (should be excluded)
        _insert_session_outcome(conn, spec_name="05_foo", touched_path=None)

        runner = _make_runner_with_conn(conn)
        paths = runner._query_prior_touched_files("05_foo")

        assert set(paths) == {"src/a.py", "src/b.py", "src/c.py"}
        # No duplicates
        assert len(paths) == len(set(paths))

    def test_excludes_null_touched_paths(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-3.1: Sessions with NULL touched_path are excluded."""

        conn = knowledge_conn_with_schema
        _insert_session_outcome(conn, spec_name="05_foo", touched_path=None)
        _insert_session_outcome(conn, spec_name="05_foo", touched_path="src/real.py")

        runner = _make_runner_with_conn(conn)
        paths = runner._query_prior_touched_files("05_foo")

        assert "src/real.py" in paths
        assert None not in paths

    def test_limits_to_50_most_recent(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-3.2: Limits result to 50 most recently touched paths."""

        conn = knowledge_conn_with_schema
        base_time = datetime(2026, 1, 1, tzinfo=UTC)

        # Insert 60 sessions with unique file paths and sequential timestamps
        for i in range(60):
            ts = (base_time + timedelta(hours=i)).isoformat()
            _insert_session_outcome(
                conn,
                spec_name="05_foo",
                touched_path=f"src/file_{i:03d}.py",
                created_at=ts,
            )

        runner = _make_runner_with_conn(conn)
        paths = runner._query_prior_touched_files("05_foo")

        assert len(paths) == 50, f"Expected 50 paths, got {len(paths)}"

    def test_most_recent_50_paths_returned(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-3.2: The 50 paths correspond to the 50 most recently created sessions."""

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

        runner = _make_runner_with_conn(conn)
        paths = runner._query_prior_touched_files("05_foo")

        # The 50 most recent are files 10-59 (indices 10..59)
        returned_set = set(paths)
        for i in range(10, 60):
            assert f"src/file_{i:03d}.py" in returned_set, (
                f"Expected recent file src/file_{i:03d}.py in result"
            )
        # The 10 oldest (0..9) should NOT be in the result
        for i in range(10):
            assert f"src/file_{i:03d}.py" not in returned_set, (
                f"Old file src/file_{i:03d}.py should not be in result"
            )

    def test_empty_when_no_prior_sessions(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-3.3: Returns empty list when no prior sessions exist.

        Requirements: 113-REQ-3.E1
        """

        conn = knowledge_conn_with_schema
        runner = _make_runner_with_conn(conn)
        paths = runner._query_prior_touched_files("05_foo")

        assert paths == []


class TestBuildPromptsPassesTouchedFiles:
    """TS-3.4: Integration — _build_prompts passes touched files to retriever."""

    def test_retriever_receives_touched_files(
        self,
        tmp_path: Path,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-3.4: AdaptiveRetriever.retrieve is called with non-empty touched_files."""

        conn = knowledge_conn_with_schema
        # Seed prior sessions for spec "05_foo"
        _insert_session_outcome(conn, spec_name="05_foo", touched_path="src/main.py,src/utils.py")

        retrieved_touched_files: list[list[str]] = []

        def capture_retrieve(*args, **kwargs):
            retrieved_touched_files.append(kwargs.get("touched_files", []))
            from agent_fox.knowledge.retrieval import IntentProfile, RetrievalResult

            return RetrievalResult(
                context="## Knowledge Context\n",
                intent_profile=IntentProfile(),
                anchor_count=0,
                signal_counts={},
            )

        runner = _make_runner_with_conn(conn)
        runner._spec_name = "05_foo"
        runner._node_id = "05_foo:1"

        with patch(
            "agent_fox.knowledge.retrieval.AdaptiveRetriever.retrieve",
            side_effect=capture_retrieve,
        ):
            try:
                runner._build_prompts(tmp_path, 1, None)
            except Exception:
                # _build_prompts may fail for unrelated reasons (spec dir missing, etc.)
                # but we care that retrieve() was called with touched_files
                pass

        assert len(retrieved_touched_files) > 0, "AdaptiveRetriever.retrieve was never called"
        assert any(len(tf) > 0 for tf in retrieved_touched_files), (
            "touched_files was always empty; expected non-empty list from prior sessions"
        )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_runner_with_conn(conn: duckdb.DuckDBPyConnection):
    """Create a NodeSessionRunner with the given DB connection."""
    from agent_fox.core.config import KnowledgeConfig
    from agent_fox.engine.session_lifecycle import NodeSessionRunner
    from agent_fox.knowledge.db import KnowledgeDB

    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = conn

    config = KnowledgeConfig()

    runner = NodeSessionRunner.__new__(NodeSessionRunner)
    runner._node_id = "05_foo:1"
    runner._spec_name = "05_foo"
    runner._run_id = "test-run"
    runner._config = config
    runner._knowledge_db = db
    runner._sink_dispatcher = None
    runner._embedder = None
    runner._archetype = "coder"
    return runner
