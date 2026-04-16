"""Tests for MemoryStore DuckDB hardening.

Test Spec: TS-38-5, TS-38-9
Requirements: 38-REQ-2.2, 38-REQ-2.4, 38-REQ-3.2
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import get_type_hints
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.ingest import KnowledgeIngestor
from agent_fox.knowledge.store import MemoryStore


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
        import agent_fox.knowledge.store as store_mod
        from agent_fox.knowledge.embeddings import EmbeddingGenerator

        ns = {**vars(store_mod), "EmbeddingGenerator": EmbeddingGenerator}
        hints = get_type_hints(MemoryStore.__init__, globalns=ns)
        assert hints["db_conn"] is duckdb.DuckDBPyConnection


class TestMemoryStorePropagation:
    """Verify MemoryStore propagates DuckDB write errors.

    Requirement: 38-REQ-3.2
    """

    def test_write_fact_propagates_duckdb_error(self, tmp_path: Path) -> None:
        """TS-38-9: write_fact propagates DuckDB error (DuckDB-only, no JSONL)."""
        jsonl_path = tmp_path / "memory.jsonl"

        # Create a mock connection that raises on execute
        failing_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        failing_conn.execute.side_effect = duckdb.Error("DuckDB write failed")

        store = MemoryStore(jsonl_path, db_conn=failing_conn)
        fact = _make_fact()

        with pytest.raises(duckdb.Error, match="DuckDB write failed"):
            store.write_fact(fact)

        # JSONL should NOT have been written (39-REQ-3.1)
        assert not jsonl_path.exists()

    def test_mark_superseded_propagates_duckdb_error(self) -> None:
        """TS-38-9: mark_superseded propagates DuckDB errors."""
        failing_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        failing_conn.execute.side_effect = duckdb.Error("DuckDB update failed")

        store = MemoryStore(Path("/dev/null"), db_conn=failing_conn)

        with pytest.raises(duckdb.Error, match="DuckDB update failed"):
            store.mark_superseded("old-id", "new-id")


class TestEmbeddingDimAllowlist:
    """Verify embedding dimension interpolation is guarded by allowlist assertions.

    Regression tests for issue #346 (SQL injection via f-string dim interpolation).
    """

    def test_write_embedding_raises_for_invalid_dim(self) -> None:
        """Invalid embedding dimensions must be rejected before SQL interpolation."""
        invalid_embedder = MagicMock()
        invalid_embedder.embedding_dimensions = 999  # not in allowlist

        mock_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        store = MemoryStore(Path("/dev/null"), db_conn=mock_conn, embedder=invalid_embedder)

        with pytest.raises(AssertionError, match="Invalid embedding dimension: 999"):
            store._write_embedding(str(uuid.uuid4()), [0.0] * 999)

        # The DB must NOT have been called — assertion fires before execute()
        mock_conn.execute.assert_not_called()

    @pytest.mark.parametrize("dim", [384, 768, 1536])
    def test_write_embedding_allows_valid_dims(self, dim: int) -> None:
        """Allowed embedding dimensions (384, 768, 1536) must not raise."""
        valid_embedder = MagicMock()
        valid_embedder.embedding_dimensions = dim

        mock_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        store = MemoryStore(Path("/dev/null"), db_conn=mock_conn, embedder=valid_embedder)

        fact_id = str(uuid.uuid4())
        embedding = [0.1] * dim
        # Should not raise
        store._write_embedding(fact_id, embedding)
        mock_conn.execute.assert_called_once()

    def test_ingest_store_embedding_raises_for_invalid_dim(
        self, tmp_path: Path, schema_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """KnowledgeIngestor._store_embedding rejects dimensions not in allowlist."""
        invalid_embedder = MagicMock()
        invalid_embedder.embedding_dimensions = 42  # not in allowlist
        invalid_embedder.embed_text.return_value = [0.0] * 42

        ingestor = KnowledgeIngestor(
            conn=schema_conn,
            embedder=invalid_embedder,
            project_root=tmp_path,
        )

        with pytest.raises(AssertionError, match="Invalid embedding dimension: 42"):
            ingestor._store_embedding(str(uuid.uuid4()), "test text", "label")
