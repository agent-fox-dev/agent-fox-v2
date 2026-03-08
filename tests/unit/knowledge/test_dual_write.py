"""Tests for dual-write fact persistence.

Test Spec: TS-12-8 (writes both), TS-12-9 (continues on DuckDB failure),
           TS-12-10 (stores without embedding), TS-12-17 (supersession)
Requirements: 12-REQ-1.1, 12-REQ-1.3, 12-REQ-1.E1, 12-REQ-2.E1,
              12-REQ-7.1
"""

from __future__ import annotations

import json
import logging
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


class TestDualWriteBothStores:
    """TS-12-8: Dual-write writes to both JSONL and DuckDB.

    Requirements: 12-REQ-1.1, 12-REQ-1.3
    """

    def test_fact_in_jsonl(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify fact appears in the JSONL file after write."""
        from agent_fox.memory.memory import MemoryStore  # type: ignore[attr-error]

        jsonl_path = tmp_path / "memory.jsonl"
        fact = make_sample_fact(fact_id=FACT_AAA, content="Test dual-write fact")

        store = MemoryStore(jsonl_path, db_conn=schema_conn, embedder=mock_embedder)
        store.write_fact(fact)

        # Check JSONL
        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) >= 1
        data = json.loads(lines[-1])
        assert data["id"] == FACT_AAA

    def test_fact_in_duckdb(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify fact appears in DuckDB memory_facts with all provenance."""
        from agent_fox.memory.memory import MemoryStore  # type: ignore[attr-error]

        jsonl_path = tmp_path / "memory.jsonl"
        fact = make_sample_fact(
            fact_id=FACT_AAA,
            content="Test dual-write fact",
            category="decision",
            spec_name="11_duckdb",
        )

        store = MemoryStore(jsonl_path, db_conn=schema_conn, embedder=mock_embedder)
        store.write_fact(fact)

        # Check DuckDB
        row = schema_conn.execute(
            "SELECT CAST(id AS VARCHAR), content, category, spec_name "
            "FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [FACT_AAA],
        ).fetchone()
        assert row is not None
        assert row[1] == "Test dual-write fact"
        assert row[2] == "decision"
        assert row[3] == "11_duckdb"

    def test_embedding_stored(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify embedding appears in memory_embeddings."""
        from agent_fox.memory.memory import MemoryStore  # type: ignore[attr-error]

        jsonl_path = tmp_path / "memory.jsonl"
        fact = make_sample_fact(fact_id=FACT_AAA)

        store = MemoryStore(jsonl_path, db_conn=schema_conn, embedder=mock_embedder)
        store.write_fact(fact)

        emb = schema_conn.execute(
            "SELECT id FROM memory_embeddings WHERE CAST(id AS VARCHAR) = ?",
            [FACT_AAA],
        ).fetchone()
        assert emb is not None


class TestDualWriteContinuesOnDuckDBFailure:
    """TS-12-9: Dual-write continues on DuckDB failure.

    Requirement: 12-REQ-1.E1
    """

    def test_jsonl_written_without_duckdb(
        self,
        tmp_path: Path,
    ) -> None:
        """Verify JSONL write succeeds when DuckDB is None."""
        from agent_fox.memory.memory import MemoryStore  # type: ignore[attr-error]

        jsonl_path = tmp_path / "memory.jsonl"
        fact = make_sample_fact(fact_id=FACT_AAA)

        store = MemoryStore(jsonl_path, db_conn=None, embedder=None)
        store.write_fact(fact)

        # Fact should be in JSONL
        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) >= 1
        data = json.loads(lines[-1])
        assert data["id"] == FACT_AAA

    def test_no_exception_raised(self, tmp_path: Path) -> None:
        """Verify no exception when DuckDB is unavailable."""
        from agent_fox.memory.memory import MemoryStore  # type: ignore[attr-error]

        jsonl_path = tmp_path / "memory.jsonl"
        fact = make_sample_fact(fact_id=FACT_AAA)

        store = MemoryStore(jsonl_path, db_conn=None, embedder=None)
        # Should not raise
        store.write_fact(fact)

    def test_warning_logged(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verify a warning is logged about DuckDB unavailability."""
        from agent_fox.memory.memory import MemoryStore  # type: ignore[attr-error]

        jsonl_path = tmp_path / "memory.jsonl"
        fact = make_sample_fact(fact_id=FACT_AAA)

        store = MemoryStore(jsonl_path, db_conn=None, embedder=None)
        with caplog.at_level(logging.WARNING):
            store.write_fact(fact)

        assert (
            "warning" in caplog.text.lower()
            or "duckdb" in caplog.text.lower()
            or "unavailable" in caplog.text.lower()
        )


class TestDualWriteWithoutEmbedding:
    """TS-12-10: Dual-write stores fact without embedding on API failure.

    Requirement: 12-REQ-2.E1
    """

    def test_fact_in_jsonl_without_embedding(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Verify fact in JSONL when embedding fails."""
        from agent_fox.memory.memory import MemoryStore  # type: ignore[attr-error]

        jsonl_path = tmp_path / "memory.jsonl"
        mock_embedder = MagicMock(spec=EmbeddingGenerator)
        mock_embedder.embed_text.return_value = None  # embedding failure

        fact = make_sample_fact(fact_id=FACT_AAA)
        store = MemoryStore(jsonl_path, db_conn=schema_conn, embedder=mock_embedder)
        store.write_fact(fact)

        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) >= 1

    def test_fact_in_duckdb_without_embedding(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Verify fact in memory_facts but no row in memory_embeddings."""
        from agent_fox.memory.memory import MemoryStore  # type: ignore[attr-error]

        jsonl_path = tmp_path / "memory.jsonl"
        mock_embedder = MagicMock(spec=EmbeddingGenerator)
        mock_embedder.embed_text.return_value = None  # embedding failure

        fact = make_sample_fact(fact_id=FACT_AAA)
        store = MemoryStore(jsonl_path, db_conn=schema_conn, embedder=mock_embedder)
        store.write_fact(fact)

        # Fact in memory_facts
        row = schema_conn.execute(
            "SELECT CAST(id AS VARCHAR) FROM memory_facts "
            "WHERE CAST(id AS VARCHAR) = ?",
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
        from agent_fox.memory.memory import MemoryStore  # type: ignore[attr-error]

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
            "SELECT CAST(superseded_by AS VARCHAR) "
            "FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [FACT_AAA],
        ).fetchone()
        assert row is not None
        assert row[0] == FACT_BBB
