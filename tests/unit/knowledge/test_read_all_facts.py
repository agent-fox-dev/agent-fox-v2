"""Tests for read_all_facts() with automatic fallback.

Verifies the 3-tier fallback: provided conn → read-only DuckDB → JSONL.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import duckdb
import pytest

from agent_fox.knowledge.store import read_all_facts
from tests.unit.knowledge.conftest import create_schema


def _insert_fact(conn: duckdb.DuckDBPyConnection, content: str = "test") -> str:
    """Insert a fact and return its id."""
    fact_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO memory_facts (id, content, category, spec_name, "
        "confidence, created_at) "
        "VALUES (?::UUID, ?, 'pattern', 'test', 0.9, CURRENT_TIMESTAMP)",
        [fact_id, content],
    )
    return fact_id


class TestReadAllFactsFromConnection:
    """Tier 1: use the provided DuckDB connection."""

    def test_returns_facts_from_provided_conn(self) -> None:
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        _insert_fact(conn, "from conn")

        facts = read_all_facts(conn, db_path=Path("/nonexistent.duckdb"))
        assert len(facts) == 1
        assert facts[0].content == "from conn"
        conn.close()

    def test_empty_db_returns_empty(self) -> None:
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        facts = read_all_facts(conn, db_path=Path("/nonexistent.duckdb"))
        assert facts == []
        conn.close()


class TestReadAllFactsFallbackToReadOnlyDB:
    """Tier 2: fall back to read-only DuckDB when conn is None."""

    def test_reads_from_db_file_when_conn_is_none(self, tmp_path: Path) -> None:
        db_path = tmp_path / "knowledge.duckdb"
        conn = duckdb.connect(str(db_path))
        create_schema(conn)
        _insert_fact(conn, "from file")
        conn.close()

        facts = read_all_facts(None, db_path=db_path)
        assert len(facts) == 1
        assert facts[0].content == "from file"

    def test_falls_through_when_db_missing(self, tmp_path: Path) -> None:
        db_path = tmp_path / "nonexistent.duckdb"

        facts = read_all_facts(None, db_path=db_path)
        assert facts == []


class TestReadAllFactsFallbackOnConnFailure:
    """Tier 1 failure triggers tier 2/3 fallback."""

    def test_falls_back_to_db_file_on_conn_error(self, tmp_path: Path) -> None:
        # Create a valid DB file
        db_path = tmp_path / "knowledge.duckdb"
        conn = duckdb.connect(str(db_path))
        create_schema(conn)
        _insert_fact(conn, "from file fallback")
        conn.close()

        # Create a broken connection (closed)
        broken_conn = duckdb.connect(":memory:")
        broken_conn.close()

        facts = read_all_facts(broken_conn, db_path=db_path)
        assert len(facts) == 1
        assert facts[0].content == "from file fallback"

