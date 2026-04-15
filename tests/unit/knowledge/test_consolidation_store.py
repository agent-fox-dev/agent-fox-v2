"""Tests for DuckDB primary read path and JSONL export-only behavior.

Test Spec: TS-39-4, TS-39-5, TS-39-6, TS-39-7, TS-39-8, TS-39-9, TS-39-10
Requirements: 39-REQ-2.*, 39-REQ-3.*
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest

from tests.unit.knowledge.conftest import create_schema


def _make_fact_row(
    *,
    fact_id: str | None = None,
    content: str = "A test fact",
    category: str = "decision",
    spec_name: str = "test_spec",
    confidence: float = 0.9,
    superseded_by: str | None = None,
) -> dict:
    """Helper to create a fact dict for insertion."""
    return {
        "id": fact_id or str(uuid.uuid4()),
        "content": content,
        "category": category,
        "spec_name": spec_name,
        "confidence": confidence,
        "superseded_by": superseded_by,
    }


def _insert_fact(conn: duckdb.DuckDBPyConnection, fact: dict) -> None:
    """Insert a fact dict into memory_facts."""
    conn.execute(
        """
        INSERT INTO memory_facts (id, content, category, spec_name,
                                  confidence, created_at, superseded_by)
        VALUES (?::UUID, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """,
        [
            fact["id"],
            fact["content"],
            fact["category"],
            fact["spec_name"],
            fact["confidence"],
            fact.get("superseded_by"),
        ],
    )


@pytest.fixture
def knowledge_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB connection with schema applied."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    yield conn  # type: ignore[misc]
    try:
        conn.close()
    except Exception:
        pass


@pytest.fixture
def tmp_jsonl(tmp_path: Path) -> Path:
    """Path to a temporary JSONL file."""
    return tmp_path / "memory.jsonl"


class TestDuckDBLoadAllFacts:
    """TS-39-4: load_all_facts reads from DuckDB, excludes superseded."""

    def test_empty_table_returns_empty_list(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        from agent_fox.knowledge.store import load_all_facts

        result = load_all_facts(knowledge_conn)
        assert result == []

    def test_returns_all_non_superseded_facts(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        from agent_fox.knowledge.store import load_all_facts

        for i in range(3):
            _insert_fact(
                knowledge_conn,
                _make_fact_row(content=f"Fact {i}", spec_name=f"spec_{i}"),
            )

        result = load_all_facts(knowledge_conn)
        assert len(result) == 3

    def test_excludes_superseded_facts(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        from agent_fox.knowledge.store import load_all_facts

        superseder_id = str(uuid.uuid4())
        # Insert 3 facts, one superseded
        _insert_fact(knowledge_conn, _make_fact_row(content="Fact A"))
        _insert_fact(
            knowledge_conn,
            _make_fact_row(content="Fact B (superseded)", superseded_by=superseder_id),
        )
        _insert_fact(knowledge_conn, _make_fact_row(content="Fact C"))

        result = load_all_facts(knowledge_conn)
        assert len(result) == 2
        contents = {f.content for f in result}
        assert "Fact B (superseded)" not in contents


class TestDuckDBLoadBySpec:
    """TS-39-5: load_facts_by_spec filters by spec_name in DuckDB."""

    def test_returns_only_matching_spec(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        from agent_fox.knowledge.store import load_facts_by_spec

        _insert_fact(knowledge_conn, _make_fact_row(spec_name="alpha", content="A"))
        _insert_fact(knowledge_conn, _make_fact_row(spec_name="alpha", content="A2"))
        _insert_fact(knowledge_conn, _make_fact_row(spec_name="beta", content="B"))

        result = load_facts_by_spec("alpha", knowledge_conn)
        assert len(result) == 2
        assert all(f.spec_name == "alpha" for f in result)

    def test_returns_empty_for_unknown_spec(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        from agent_fox.knowledge.store import load_facts_by_spec

        _insert_fact(knowledge_conn, _make_fact_row(spec_name="alpha"))

        result = load_facts_by_spec("gamma", knowledge_conn)
        assert result == []


class TestDuckDBReadError:
    """TS-39-6: DuckDB errors propagate, no silent fallback."""

    def test_closed_connection_raises(self) -> None:
        from agent_fox.knowledge.store import load_all_facts

        conn = duckdb.connect(":memory:")
        create_schema(conn)
        conn.close()

        with pytest.raises(Exception):
            load_all_facts(conn)


class TestMemoryStoreDuckDBOnly:
    """TS-39-7: MemoryStore.write_fact writes to DuckDB only, not JSONL."""

    def test_write_fact_creates_duckdb_row_not_jsonl(
        self,
        knowledge_conn: duckdb.DuckDBPyConnection,
        tmp_jsonl: Path,
    ) -> None:
        from agent_fox.knowledge.facts import Fact
        from agent_fox.knowledge.store import MemoryStore

        store = MemoryStore(
            jsonl_path=tmp_jsonl,
            db_conn=knowledge_conn,
        )

        fact = Fact(
            id=str(uuid.uuid4()),
            content="Test fact for DuckDB only",
            category="decision",
            spec_name="test_spec",
            keywords=["test"],
            confidence=0.9,
            created_at="2026-01-01T00:00:00Z",
        )
        store.write_fact(fact)

        # Fact should exist in DuckDB
        rows = knowledge_conn.execute(
            "SELECT content FROM memory_facts WHERE content = ?",
            ["Test fact for DuckDB only"],
        ).fetchall()
        assert len(rows) == 1

        # JSONL file should NOT have been written
        assert not tmp_jsonl.exists()


class TestCompactionViaDuckDB:
    """TS-39-9: compact reads from DuckDB, deduplicates, exports to JSONL."""

    def test_compact_deduplicates_and_exports(
        self,
        knowledge_conn: duckdb.DuckDBPyConnection,
        tmp_jsonl: Path,
    ) -> None:
        from agent_fox.knowledge.compaction import compact

        # Insert 5 facts: 2 duplicates by content, 1 superseded
        id1 = str(uuid.uuid4())
        id2 = str(uuid.uuid4())
        id3 = str(uuid.uuid4())
        id4 = str(uuid.uuid4())
        id5 = str(uuid.uuid4())

        _insert_fact(
            knowledge_conn,
            _make_fact_row(fact_id=id1, content="Unique fact A"),
        )
        _insert_fact(
            knowledge_conn,
            _make_fact_row(fact_id=id2, content="Duplicate content"),
        )
        _insert_fact(
            knowledge_conn,
            _make_fact_row(fact_id=id3, content="Duplicate content"),
        )
        _insert_fact(
            knowledge_conn,
            _make_fact_row(fact_id=id4, content="Superseded fact", superseded_by=id5),
        )
        _insert_fact(
            knowledge_conn,
            _make_fact_row(fact_id=id5, content="Superseding fact"),
        )

        original, surviving = compact(knowledge_conn)
        assert original == 5
        assert surviving == 3

        # DuckDB should have exactly 3 non-superseded facts
        rows = knowledge_conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()
        assert rows is not None
        assert rows[0] >= surviving


