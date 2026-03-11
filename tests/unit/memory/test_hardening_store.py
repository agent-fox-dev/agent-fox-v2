"""Tests for MemoryStore DuckDB hardening.

Test Spec: TS-38-5, TS-38-9
Requirements: 38-REQ-2.2, 38-REQ-2.4, 38-REQ-3.2
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import get_type_hints
from unittest.mock import MagicMock

import duckdb
import pytest

from agent_fox.memory.memory import MemoryStore
from agent_fox.memory.types import Fact


def _make_fact(*, fact_id: str | None = None) -> Fact:
    return Fact(
        id=fact_id or str(uuid.uuid4()),
        content="test fact",
        category="decision",
        spec_name="test_spec",
        keywords=["test"],
        confidence="high",
        created_at="2025-01-01T00:00:00Z",
        session_id="test/1",
        commit_sha="abc123",
    )


class TestMemoryStoreRequired:
    """Verify MemoryStore requires db_conn parameter.

    Requirements: 38-REQ-2.2, 38-REQ-2.4
    """

    def test_db_conn_parameter_is_required(self) -> None:
        """TS-38-5: db_conn type is non-optional."""
        import inspect

        sig = inspect.signature(MemoryStore.__init__)
        param = sig.parameters["db_conn"]
        # Must not have a default value (i.e., it's required)
        assert param.default is inspect.Parameter.empty
        # Resolve type hint — need full namespace including TYPE_CHECKING imports
        import agent_fox.memory.memory as mem_mod
        from agent_fox.knowledge.embeddings import EmbeddingGenerator

        ns = {**vars(mem_mod), "EmbeddingGenerator": EmbeddingGenerator}
        hints = get_type_hints(MemoryStore.__init__, globalns=ns)
        assert hints["db_conn"] is duckdb.DuckDBPyConnection


class TestMemoryStorePropagation:
    """Verify MemoryStore propagates DuckDB write errors.

    Requirement: 38-REQ-3.2
    """

    def test_write_fact_propagates_duckdb_error(self, tmp_path: Path) -> None:
        """TS-38-9: write_fact propagates DuckDB error after JSONL write succeeds."""
        jsonl_path = tmp_path / "memory.jsonl"

        # Create a mock connection that raises on execute
        failing_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        failing_conn.execute.side_effect = duckdb.Error("DuckDB write failed")

        store = MemoryStore(jsonl_path, db_conn=failing_conn)
        fact = _make_fact()

        with pytest.raises(duckdb.Error, match="DuckDB write failed"):
            store.write_fact(fact)

        # JSONL write should have succeeded
        assert jsonl_path.exists()
        content = jsonl_path.read_text()
        assert fact.content in content

    def test_mark_superseded_propagates_duckdb_error(self) -> None:
        """TS-38-9: mark_superseded propagates DuckDB errors."""
        failing_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        failing_conn.execute.side_effect = duckdb.Error("DuckDB update failed")

        store = MemoryStore(Path("/dev/null"), db_conn=failing_conn)

        with pytest.raises(duckdb.Error, match="DuckDB update failed"):
            store.mark_superseded("old-id", "new-id")
