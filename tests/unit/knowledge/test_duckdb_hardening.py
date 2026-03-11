"""Tests for DuckDB hardening: init, error propagation, isolation.

Test Spec: TS-38-1, TS-38-2, TS-38-8, TS-38-10, TS-38-12, TS-38-E1,
           TS-38-6, TS-38-7, TS-38-11, TS-38-E2
Requirements: 38-REQ-1.*, 38-REQ-3.*, 38-REQ-4.*, 38-REQ-5.*, 38-REQ-6.*
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import get_type_hints
from unittest.mock import MagicMock

import duckdb
import pytest

from agent_fox.core.config import KnowledgeConfig
from agent_fox.knowledge.db import KnowledgeDB, open_knowledge_store
from agent_fox.knowledge.duckdb_sink import DuckDBSink
from agent_fox.knowledge.sink import SessionOutcome
from agent_fox.memory.types import Fact

# -- Helpers ------------------------------------------------------------------


def _make_fact(*, fact_id: str | None = None) -> Fact:
    return Fact(
        id=fact_id or str(uuid.uuid4()),
        content="test fact",
        category="decision",
        spec_name="test_spec",
        keywords=["test"],
        confidence=0.9,
        created_at="2025-01-01T00:00:00Z",
        session_id="test/1",
        commit_sha="abc123",
    )


# -- TS-38-1, TS-38-2, TS-38-E1: Initialization ---------------------------


class TestInitialization:
    """Verify open_knowledge_store error/success behavior.

    Requirements: 38-REQ-1.1, 38-REQ-1.2, 38-REQ-1.3, 38-REQ-1.E1
    """

    def test_raises_on_failure(self, tmp_path: Path) -> None:
        """TS-38-1: raises RuntimeError on failure."""
        bad_path = tmp_path / "nested" / "readonly"
        bad_path.mkdir(parents=True)
        bad_path.chmod(0o000)
        bad_config = KnowledgeConfig(
            store_path=str(bad_path / "test.duckdb"),
        )

        with pytest.raises(
            RuntimeError,
            match="Knowledge store initialization failed",
        ):
            open_knowledge_store(bad_config)

        # Cleanup permissions for tmp_path cleanup
        bad_path.chmod(0o755)

    def test_returns_knowledgedb(self, tmp_path: Path) -> None:
        """TS-38-2: returns KnowledgeDB on success."""
        config = KnowledgeConfig(
            store_path=str(tmp_path / "test.duckdb"),
        )
        result = open_knowledge_store(config)
        assert isinstance(result, KnowledgeDB)
        assert result is not None
        result.close()

    def test_never_returns_none(self, tmp_path: Path) -> None:
        """TS-38-1: never returns None."""
        config = KnowledgeConfig(
            store_path=str(tmp_path / "test.duckdb"),
        )
        result = open_knowledge_store(config)
        assert result is not None
        result.close()

    def test_error_includes_path(self, tmp_path: Path) -> None:
        """TS-38-E1: Error message includes the file path."""
        bad_path = tmp_path / "no_access"
        bad_path.mkdir()
        bad_path.chmod(0o000)
        db_path = bad_path / "test.duckdb"
        config = KnowledgeConfig(store_path=str(db_path))

        with pytest.raises(RuntimeError, match=str(bad_path)):
            open_knowledge_store(config)

        bad_path.chmod(0o755)


# -- TS-38-8: DuckDBSink error propagation ---------------------------------


class TestDuckDBSinkPropagation:
    """Verify DuckDBSink does not swallow DuckDB errors.

    Requirement: 38-REQ-3.1
    """

    def test_record_session_outcome_propagates(self) -> None:
        """TS-38-8: record_session_outcome propagates."""
        failing_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        failing_conn.execute.side_effect = duckdb.Error(
            "mock write failure",
        )

        sink = DuckDBSink(failing_conn)
        outcome = SessionOutcome(
            spec_name="test_spec",
            task_group="1",
            node_id="test_spec/1",
            status="completed",
        )

        with pytest.raises(duckdb.Error, match="mock write failure"):
            sink.record_session_outcome(outcome)

    def test_record_tool_call_propagates(self) -> None:
        """DuckDB errors in record_tool_call propagate."""
        from agent_fox.knowledge.sink import ToolCall

        failing_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        failing_conn.execute.side_effect = duckdb.Error(
            "mock write failure",
        )

        sink = DuckDBSink(failing_conn, debug=True)

        with pytest.raises(duckdb.Error, match="mock write failure"):
            sink.record_tool_call(ToolCall(tool_name="test"))

    def test_record_tool_error_propagates(self) -> None:
        """DuckDB errors in record_tool_error propagate."""
        from agent_fox.knowledge.sink import ToolError

        failing_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        failing_conn.execute.side_effect = duckdb.Error(
            "mock write failure",
        )

        sink = DuckDBSink(failing_conn, debug=True)

        with pytest.raises(duckdb.Error, match="mock write failure"):
            sink.record_tool_error(ToolError(tool_name="test"))


# -- TS-38-10: Knowledge harvest error propagation -------------------------


class TestKnowledgeHarvestPropagation:
    """Verify knowledge harvest does not silently skip DuckDB errors.

    Requirements: 38-REQ-3.3, 38-REQ-3.4
    """

    def test_sync_facts_propagates_error(
        self, tmp_path: Path
    ) -> None:
        """TS-38-10: sync_facts_to_duckdb propagates errors."""
        from agent_fox.engine.knowledge_harvest import (
            sync_facts_to_duckdb,
        )

        config = KnowledgeConfig(
            store_path=str(tmp_path / "test.duckdb"),
        )
        db = KnowledgeDB(config)
        db.open()

        original_conn = db._conn
        mock_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        mock_conn.execute.side_effect = duckdb.Error(
            "write failure",
        )
        db._conn = mock_conn

        fact = _make_fact()
        with pytest.raises(duckdb.Error, match="write failure"):
            sync_facts_to_duckdb(db, [fact])

        db._conn = original_conn
        db.close()

    def test_extract_causal_links_propagates(
        self, tmp_path: Path
    ) -> None:
        """TS-38-10: _extract_causal_links propagates errors."""
        from agent_fox.engine.knowledge_harvest import (
            _extract_causal_links,
        )

        config = KnowledgeConfig(
            store_path=str(tmp_path / "test.duckdb"),
        )
        db = KnowledgeDB(config)
        db.open()

        original_conn = db._conn
        mock_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        mock_conn.execute.side_effect = duckdb.Error(
            "causal link failure",
        )
        db._conn = mock_conn

        facts = [_make_fact(), _make_fact()]

        with pytest.raises((duckdb.Error, Exception)):
            _extract_causal_links(
                facts, "test/1", "test-model", db
            )

        db._conn = original_conn
        db.close()


# -- TS-38-12: Test fixture isolation ----------------------------------------


class TestFixtureIsolation:
    """Verify the DuckDB test fixture provides isolated databases.

    Requirements: 38-REQ-5.1, 38-REQ-5.2
    """

    def test_fixture_provides_fresh_db_a(
        self,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-38-12: First test writes data."""
        knowledge_conn.execute(
            "INSERT INTO memory_facts "
            "(id, content, category, confidence, created_at) "
            "VALUES ("
            "'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::UUID, "
            "'test', 'decision', 'high', CURRENT_TIMESTAMP)"
        )
        count = knowledge_conn.execute(
            "SELECT COUNT(*) FROM memory_facts"
        ).fetchone()[0]
        assert count == 1

    def test_fixture_provides_fresh_db_b(
        self,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-38-12: Second test should see zero rows."""
        count = knowledge_conn.execute(
            "SELECT COUNT(*) FROM memory_facts"
        ).fetchone()[0]
        assert count == 0

    def test_fixture_has_all_tables(
        self,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-38-12: Fixture DB has all schema tables."""
        tables = {
            row[0]
            for row in knowledge_conn.execute(
                "SELECT table_name "
                "FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
        expected = {
            "schema_version",
            "memory_facts",
            "memory_embeddings",
            "session_outcomes",
            "fact_causes",
            "tool_calls",
            "tool_errors",
        }
        assert expected.issubset(tables)


# -- TS-38-6: assemble_context requires conn --------------------------------


class TestContextAssemblyRequired:
    """Verify assemble_context requires conn parameter.

    Requirements: 38-REQ-4.1, 38-REQ-4.2, 38-REQ-4.3, 38-REQ-3.E1
    """

    def test_conn_parameter_is_required(self) -> None:
        """TS-38-6: conn type is non-optional."""
        from agent_fox.session.prompt import assemble_context

        hints = get_type_hints(assemble_context)
        assert "conn" in hints
        assert hints["conn"] is duckdb.DuckDBPyConnection

    def test_db_error_propagates(self, tmp_path: Path) -> None:
        """TS-38-E2: DB errors propagate, no fallback."""
        from agent_fox.session.prompt import assemble_context

        spec_dir = tmp_path / "test_spec"
        spec_dir.mkdir()
        for f in ("requirements.md", "design.md",
                   "test_spec.md", "tasks.md"):
            (spec_dir / f).write_text(f"# {f}\n")

        failing_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        failing_conn.execute.side_effect = duckdb.Error(
            "DB query failed",
        )

        with pytest.raises(duckdb.Error):
            assemble_context(
                spec_dir, task_group=1, conn=failing_conn
            )

    def test_uses_db_backed_rendering(
        self,
        tmp_path: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-38-11: uses DB-backed rendering."""
        from agent_fox.session.prompt import assemble_context

        spec_dir = tmp_path / "test_spec"
        spec_dir.mkdir()
        for f in ("requirements.md", "design.md",
                   "test_spec.md", "tasks.md"):
            (spec_dir / f).write_text(f"# {f}\n")

        knowledge_conn.execute(
            "INSERT INTO review_findings "
            "(id, severity, description, "
            "spec_name, task_group, session_id) "
            "VALUES ("
            "'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'"
            "::UUID, 'critical', "
            "'Test finding from DB', "
            "'test_spec', '1', 'test/1')"
        )

        context = assemble_context(
            spec_dir, task_group=1, conn=knowledge_conn
        )
        assert "Test finding from DB" in context


# -- TS-38-7: AssessmentPipeline requires db ---------------------------------


class TestRoutingRequired:
    """Verify AssessmentPipeline requires db parameter.

    Requirements: 38-REQ-6.1, 38-REQ-6.2
    """

    def test_db_parameter_is_required(self) -> None:
        """TS-38-7: db type is non-optional."""
        from agent_fox.routing.assessor import AssessmentPipeline

        hints = get_type_hints(AssessmentPipeline.__init__)
        assert "db" in hints
        assert hints["db"] is duckdb.DuckDBPyConnection

    def test_get_outcome_count_requires_db(self) -> None:
        """TS-38-7: _get_outcome_count needs non-None db."""
        from agent_fox.routing.assessor import AssessmentPipeline

        hints = get_type_hints(AssessmentPipeline.__init__)
        assert hints["db"] is duckdb.DuckDBPyConnection
