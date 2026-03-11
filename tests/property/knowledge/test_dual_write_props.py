"""Property tests for dual-write consistency and embedding non-fatality.

Test Spec: TS-12-P1 (dual-write consistency),
           TS-12-P2 (embedding non-fatality)
Properties: Property 1, Property 2 from design.md
Requirements: 12-REQ-1.1, 12-REQ-1.2, 12-REQ-1.E1, 12-REQ-2.E1
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.memory.types import Fact

# -- Helpers -----------------------------------------------------------------


def _fresh_schema_conn() -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DuckDB with schema for hypothesis examples."""
    from tests.unit.knowledge.conftest import create_schema

    conn = duckdb.connect(":memory:")
    create_schema(conn)
    return conn


def _make_embedding(seed: int) -> list[float]:
    """Create a deterministic 1024-dim embedding for testing."""
    raw = [math.sin(seed * (i + 1) * 0.1) for i in range(1024)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw] if norm > 0 else [1.0 / math.sqrt(1024)] * 1024


# -- Hypothesis strategies ---------------------------------------------------

fact_content = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=200,
)

fact_category = st.sampled_from(
    ["gotcha", "pattern", "decision", "convention", "anti_pattern", "fragile_area"]
)


@st.composite
def random_memory_fact(draw: st.DrawFn) -> Fact:
    """Generate a random valid Fact for property testing."""
    import uuid

    fact_id = str(uuid.uuid4())
    content = draw(fact_content)
    category = draw(fact_category)

    return Fact(
        id=fact_id,
        content=content,
        category=category,
        spec_name="test_spec",
        keywords=["test"],
        confidence=0.9,
        created_at="2025-11-01T10:00:00Z",
        supersedes=None,
    )


# -- Property Tests ----------------------------------------------------------


class TestDualWriteConsistency:
    """TS-12-P1: Dual-write consistency.

    Property 1: For any fact, after write_fact(), the fact is always
    present in JSONL. If DuckDB is available, it is also in memory_facts.

    Requirements: 12-REQ-1.1, 12-REQ-1.2, 12-REQ-1.E1
    """

    @given(fact=random_memory_fact())
    @settings(max_examples=10, deadline=None)
    def test_fact_always_in_jsonl(self, fact: Fact) -> None:
        """For any fact, it is always present in JSONL after write."""
        from agent_fox.memory.memory import MemoryStore  # type: ignore[attr-error]

        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "memory.jsonl"
            conn = _fresh_schema_conn()

            mock_embedder = MagicMock(spec=EmbeddingGenerator)
            mock_embedder.embed_text.return_value = _make_embedding(1)

            store = MemoryStore(jsonl_path, db_conn=conn, embedder=mock_embedder)
            store.write_fact(fact)

            # Assert: fact in JSONL
            lines = jsonl_path.read_text().strip().split("\n")
            found = any(json.loads(line)["id"] == fact.id for line in lines)
            assert found, f"Fact {fact.id} not found in JSONL"

            conn.close()

    @given(fact=random_memory_fact())
    @settings(max_examples=10, deadline=None)
    def test_fact_in_duckdb_when_available(self, fact: Fact) -> None:
        """If DuckDB is non-None, fact exists in memory_facts after write."""
        from agent_fox.memory.memory import MemoryStore  # type: ignore[attr-error]

        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "memory.jsonl"
            conn = _fresh_schema_conn()

            mock_embedder = MagicMock(spec=EmbeddingGenerator)
            mock_embedder.embed_text.return_value = _make_embedding(1)

            store = MemoryStore(jsonl_path, db_conn=conn, embedder=mock_embedder)
            store.write_fact(fact)

            # Assert: fact in DuckDB
            row = conn.execute(
                "SELECT CAST(id AS VARCHAR) FROM memory_facts "
                "WHERE CAST(id AS VARCHAR) = ?",
                [fact.id],
            ).fetchone()
            assert row is not None, f"Fact {fact.id} not found in DuckDB"

            conn.close()


class TestEmbeddingNonFatality:
    """TS-12-P2: Embedding non-fatality.

    Property 2: For any fact where embedding fails, the fact is still
    written to JSONL and DuckDB. No exception propagates.

    Requirement: 12-REQ-2.E1
    """

    @given(fact=random_memory_fact(), embed_succeeds=st.booleans())
    @settings(max_examples=20, deadline=None)
    def test_fact_persisted_regardless_of_embedding(
        self, fact: Fact, embed_succeeds: bool
    ) -> None:
        """Fact is always in JSONL and DuckDB regardless of embedding success."""
        from agent_fox.memory.memory import MemoryStore  # type: ignore[attr-error]

        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "memory.jsonl"
            conn = _fresh_schema_conn()

            mock_embedder = MagicMock(spec=EmbeddingGenerator)
            if embed_succeeds:
                mock_embedder.embed_text.return_value = _make_embedding(1)
            else:
                mock_embedder.embed_text.return_value = None

            store = MemoryStore(jsonl_path, db_conn=conn, embedder=mock_embedder)
            # Should never raise
            store.write_fact(fact)

            # Assert: fact in JSONL
            lines = jsonl_path.read_text().strip().split("\n")
            found_jsonl = any(json.loads(line)["id"] == fact.id for line in lines)
            assert found_jsonl

            # Assert: fact in DuckDB
            row = conn.execute(
                "SELECT CAST(id AS VARCHAR) FROM memory_facts "
                "WHERE CAST(id AS VARCHAR) = ?",
                [fact.id],
            ).fetchone()
            assert row is not None

            conn.close()
