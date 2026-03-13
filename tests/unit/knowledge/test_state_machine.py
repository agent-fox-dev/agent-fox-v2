"""Tests for KnowledgeStateMachine: buffered writes with flush semantics.

Test Spec: TS-39-11, TS-39-12, TS-39-13, TS-39-14
Requirements: 39-REQ-4.*
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import duckdb
import pytest

from tests.unit.knowledge.conftest import create_schema


def _make_fact(content: str = "Test fact"):  # -> Fact
    """Create a Fact for state machine testing."""
    from agent_fox.knowledge.facts import Fact

    return Fact(
        id=str(uuid.uuid4()),
        content=content,
        category="decision",
        spec_name="test_spec",
        keywords=["test"],
        confidence=0.9,
        created_at="2026-01-01T00:00:00Z",
    )


@pytest.fixture
def knowledge_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection with schema applied."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    yield conn  # type: ignore[misc]
    try:
        conn.close()
    except Exception:
        pass


@pytest.fixture
def memory_store(knowledge_conn: duckdb.DuckDBPyConnection, tmp_path):
    """A MemoryStore backed by the in-memory DuckDB connection."""
    from agent_fox.knowledge.store import MemoryStore

    return MemoryStore(
        jsonl_path=tmp_path / "memory.jsonl",
        db_conn=knowledge_conn,
    )


@pytest.fixture
def state_machine(memory_store):
    """A KnowledgeStateMachine backed by memory_store."""
    from agent_fox.knowledge.state_machine import KnowledgeStateMachine

    return KnowledgeStateMachine(store=memory_store)


class TestAddFact:
    """TS-39-11: add_fact buffers without writing to DuckDB."""

    def test_add_fact_buffers_in_pending(self, state_machine, knowledge_conn) -> None:

        fact = _make_fact("Buffered fact")
        state_machine.add_fact(fact)

        # Fact should be in pending
        assert len(state_machine.pending) == 1
        assert state_machine.pending[0].content == "Buffered fact"

        # Fact should NOT be in DuckDB yet
        rows = knowledge_conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()
        assert rows is not None
        assert rows[0] == 0


class TestFlush:
    """TS-39-12: flush writes all buffered facts to DuckDB."""

    def test_flush_writes_all_and_clears_buffer(
        self, state_machine, knowledge_conn
    ) -> None:
        facts = [_make_fact(f"Fact {i}") for i in range(3)]
        for f in facts:
            state_machine.add_fact(f)

        result = state_machine.flush()
        assert result == 3
        assert state_machine.pending == []

        # All 3 facts should be in DuckDB
        rows = knowledge_conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()
        assert rows is not None
        assert rows[0] == 3


class TestFlushEmpty:
    """TS-39-13: flush on empty buffer is a no-op."""

    def test_flush_empty_returns_zero(self, state_machine, knowledge_conn) -> None:
        result = state_machine.flush()
        assert result == 0
        assert state_machine.pending == []

        # No DuckDB writes
        rows = knowledge_conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()
        assert rows is not None
        assert rows[0] == 0


class TestPartialFlushFailure:
    """TS-39-14: partial flush failure keeps unwritten facts in buffer."""

    def test_partial_failure_retains_unwritten(
        self, state_machine, memory_store, knowledge_conn
    ) -> None:
        facts = [_make_fact(f"Fact {i}") for i in range(3)]
        for f in facts:
            state_machine.add_fact(f)

        call_count = 0
        original_write_fact = memory_store.write_fact

        def failing_write_fact(fact):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                raise RuntimeError("DuckDB write failed on 3rd fact")
            return original_write_fact(fact)

        with patch.object(memory_store, "write_fact", side_effect=failing_write_fact):
            with pytest.raises(RuntimeError, match="DuckDB write failed"):
                state_machine.flush()

        # Only the 3rd fact should remain in pending
        assert len(state_machine.pending) == 1
        assert state_machine.pending[0].content == "Fact 2"

        # First 2 facts should be in DuckDB
        rows = knowledge_conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()
        assert rows is not None
        assert rows[0] == 2
