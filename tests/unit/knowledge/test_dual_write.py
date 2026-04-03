"""Tests for DuckDB-primary fact persistence.

Test Spec: TS-12-8 (writes to DuckDB), TS-12-9 (DuckDB error propagation),
           TS-12-10 (stores without embedding), TS-12-17 (supersession)
Requirements: 12-REQ-1.1, 12-REQ-1.3, 12-REQ-1.E1, 12-REQ-2.E1,
              12-REQ-7.1, 39-REQ-3.1
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest

from agent_fox.knowledge.embeddings import EmbeddingGenerator

from .conftest import (
    FACT_AAA,
    FACT_BBB,
    make_sample_fact,
)


class TestDuckDBWrite:
    """TS-12-8: write_fact writes to DuckDB (not JSONL per 39-REQ-3.1).

    Requirements: 12-REQ-1.1, 12-REQ-1.3, 39-REQ-3.1
    """

    def test_fact_in_duckdb(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify fact appears in DuckDB memory_facts with all provenance."""
        from agent_fox.knowledge.store import MemoryStore

        jsonl_path = tmp_path / "memory.jsonl"
        fact = make_sample_fact(
            fact_id=FACT_AAA,
            content="Test DuckDB write fact",
            category="decision",
            spec_name="11_duckdb",
        )

        store = MemoryStore(jsonl_path, db_conn=schema_conn, embedder=mock_embedder)
        store.write_fact(fact)

        # Check DuckDB
        row = schema_conn.execute(
            "SELECT CAST(id AS VARCHAR), content, category, spec_name FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [FACT_AAA],
        ).fetchone()
        assert row is not None
        assert row[1] == "Test DuckDB write fact"
        assert row[2] == "decision"
        assert row[3] == "11_duckdb"

    def test_no_jsonl_write(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify JSONL is NOT written during write_fact (39-REQ-3.1)."""
        from agent_fox.knowledge.store import MemoryStore

        jsonl_path = tmp_path / "memory.jsonl"
        fact = make_sample_fact(fact_id=FACT_AAA, content="Test fact")

        store = MemoryStore(jsonl_path, db_conn=schema_conn, embedder=mock_embedder)
        store.write_fact(fact)

        assert not jsonl_path.exists()

    def test_embedding_stored(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify embedding appears in memory_embeddings."""
        from agent_fox.knowledge.store import MemoryStore

        jsonl_path = tmp_path / "memory.jsonl"
        fact = make_sample_fact(fact_id=FACT_AAA)

        store = MemoryStore(jsonl_path, db_conn=schema_conn, embedder=mock_embedder)
        store.write_fact(fact)

        emb = schema_conn.execute(
            "SELECT id FROM memory_embeddings WHERE CAST(id AS VARCHAR) = ?",
            [FACT_AAA],
        ).fetchone()
        assert emb is not None


class TestDuckDBWriteErrorPropagation:
    """TS-12-9 (superseded by 38-REQ-3.2): DuckDB errors propagate.

    Requirement: 38-REQ-3.2 (supersedes 12-REQ-1.E1)
    """

    def test_duckdb_error_propagates(self, tmp_path: Path) -> None:
        """Verify DuckDB error propagates (38-REQ-3.2)."""
        from unittest.mock import MagicMock

        from agent_fox.knowledge.store import MemoryStore

        jsonl_path = tmp_path / "memory.jsonl"
        fact = make_sample_fact(fact_id=FACT_AAA)

        failing_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        failing_conn.execute.side_effect = duckdb.Error("mock failure")

        store = MemoryStore(jsonl_path, db_conn=failing_conn, embedder=None)
        with pytest.raises(duckdb.Error, match="mock failure"):
            store.write_fact(fact)

    def test_successful_write(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Verify DuckDB write succeeds normally."""
        from agent_fox.knowledge.store import MemoryStore

        jsonl_path = tmp_path / "memory.jsonl"
        fact = make_sample_fact(fact_id=FACT_AAA)

        store = MemoryStore(jsonl_path, db_conn=schema_conn, embedder=None)
        store.write_fact(fact)

        # Check DuckDB
        row = schema_conn.execute(
            "SELECT CAST(id AS VARCHAR) FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [FACT_AAA],
        ).fetchone()
        assert row is not None


class TestWriteWithoutEmbedding:
    """TS-12-10: Stores fact without embedding on API failure.

    Requirement: 12-REQ-2.E1
    """

    def test_fact_in_duckdb_without_embedding(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Verify fact in memory_facts but no row in memory_embeddings."""
        from agent_fox.knowledge.store import MemoryStore

        jsonl_path = tmp_path / "memory.jsonl"
        mock_embedder = MagicMock(spec=EmbeddingGenerator)
        mock_embedder.embed_text.return_value = None  # embedding failure

        fact = make_sample_fact(fact_id=FACT_AAA)
        store = MemoryStore(jsonl_path, db_conn=schema_conn, embedder=mock_embedder)
        store.write_fact(fact)

        # Fact in memory_facts
        row = schema_conn.execute(
            "SELECT CAST(id AS VARCHAR) FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [FACT_AAA],
        ).fetchone()
        assert row is not None

        # No embedding
        emb = schema_conn.execute(
            "SELECT id FROM memory_embeddings WHERE CAST(id AS VARCHAR) = ?",
            [FACT_AAA],
        ).fetchone()
        assert emb is None


class TestSupersession:
    """TS-12-17: Supersession marks old fact correctly.

    Requirement: 12-REQ-7.1
    """

    def test_mark_superseded_updates_column(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify mark_superseded updates superseded_by column."""
        from agent_fox.knowledge.store import MemoryStore

        jsonl_path = tmp_path / "memory.jsonl"

        # Insert two facts
        old_fact = make_sample_fact(fact_id=FACT_AAA, content="Old fact")
        new_fact = make_sample_fact(fact_id=FACT_BBB, content="New fact")

        store = MemoryStore(jsonl_path, db_conn=schema_conn, embedder=mock_embedder)
        store.write_fact(old_fact)
        store.write_fact(new_fact)

        # Mark old as superseded
        store.mark_superseded(FACT_AAA, FACT_BBB)

        row = schema_conn.execute(
            "SELECT CAST(superseded_by AS VARCHAR) FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [FACT_AAA],
        ).fetchone()
        assert row is not None
        assert row[0] == FACT_BBB
