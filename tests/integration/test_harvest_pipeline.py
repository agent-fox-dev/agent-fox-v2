"""Integration tests for the knowledge harvest pipeline.

Uses real in-memory DuckDB with schema from KnowledgeDB to test end-to-end
fact insertion, embedding storage, causal link creation, and provenance.

Test Spec: TS-52-4, TS-52-6, TS-52-13, TS-52-E4
Requirements: 52-REQ-2.1, 52-REQ-3.1, 52-REQ-7.1, 52-REQ-7.E1
"""

from __future__ import annotations

import uuid

import pytest

from agent_fox.core.config import KnowledgeConfig
from agent_fox.engine.knowledge_harvest import sync_facts_to_duckdb
from agent_fox.knowledge.causal import store_causal_links
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.facts import Fact


def _make_fact(
    *,
    fact_id: str | None = None,
    content: str = "test fact",
    category: str = "gotcha",
    spec_name: str = "11_duckdb",
    session_id: str = "coder_11_1",
    commit_sha: str = "abc123",
    confidence: float = 0.9,
) -> Fact:
    return Fact(
        id=fact_id or str(uuid.uuid4()),
        content=content,
        category=category,
        spec_name=spec_name,
        keywords=["test"],
        confidence=confidence,
        created_at="2025-01-01T00:00:00Z",
        session_id=session_id,
        commit_sha=commit_sha,
    )


@pytest.fixture
def knowledge_db() -> KnowledgeDB:
    """In-memory KnowledgeDB with full schema and migrations."""
    config = KnowledgeConfig(store_path=":memory:")
    db = KnowledgeDB(config)
    db.open()
    return db


# ---------------------------------------------------------------------------
# TS-52-4: Fact provenance fields populated
# ---------------------------------------------------------------------------


class TestFactProvenance:
    """TS-52-4: Verify that inserted facts have all provenance fields
    populated (non-NULL).

    Requirement: 52-REQ-2.1
    """

    def test_all_provenance_fields_non_null(self, knowledge_db: KnowledgeDB) -> None:
        """Row in memory_facts should have all fields non-NULL except
        supersedes."""
        fact = _make_fact(
            content="DuckDB needs explicit UUID casting",
            category="gotcha",
            spec_name="11_duckdb",
            session_id="coder_11_1",
            commit_sha="abc123",
            confidence=0.9,
        )
        sync_facts_to_duckdb(knowledge_db, [fact])

        row = knowledge_db.connection.execute(
            "SELECT id::VARCHAR, content, category, spec_name, "
            "session_id, commit_sha, confidence, created_at "
            "FROM memory_facts WHERE id = ?::UUID",
            [fact.id],
        ).fetchone()

        assert row is not None, "Fact should be inserted"
        (
            fact_id,
            content,
            category,
            spec_name,
            session_id,
            commit_sha,
            confidence,
            created_at,
        ) = row
        assert fact_id is not None
        assert content is not None
        assert category is not None
        assert spec_name == "11_duckdb"
        assert session_id == "coder_11_1"
        assert commit_sha == "abc123"
        assert confidence is not None
        assert created_at is not None

    def test_provenance_values_match(self, knowledge_db: KnowledgeDB) -> None:
        """Provenance values should match what was passed in."""
        fact = _make_fact(
            content="Test provenance",
            category="pattern",
            spec_name="07_oauth",
            session_id="coder_07_3",
            commit_sha="def456",
            confidence=0.6,
        )
        sync_facts_to_duckdb(knowledge_db, [fact])

        row = knowledge_db.connection.execute(
            "SELECT category, spec_name, session_id, commit_sha, confidence "
            "FROM memory_facts WHERE id = ?::UUID",
            [fact.id],
        ).fetchone()

        assert row is not None
        assert row[0] == "pattern"
        assert row[1] == "07_oauth"
        assert row[2] == "coder_07_3"
        assert row[3] == "def456"
        assert abs(row[4] - 0.6) < 0.01


# ---------------------------------------------------------------------------
# TS-52-6: Embedding generated for new fact
# ---------------------------------------------------------------------------


class TestEmbeddingGenerated:
    """TS-52-6: Verify that embeddings are generated and stored for new facts.

    Requirement: 52-REQ-3.1

    NOTE: Embedding generation within extract_and_store_knowledge() is
    not yet implemented. This test validates the MemoryStore.write_fact()
    path which does generate embeddings.
    """

    def test_embedding_stored_via_memory_store(self, knowledge_db: KnowledgeDB) -> None:
        """MemoryStore.write_fact should store both fact and embedding."""
        from unittest.mock import MagicMock

        from agent_fox.knowledge.store import MemoryStore

        mock_embedder = MagicMock()
        mock_embedder.embedding_dimensions = 384
        mock_embedder.embed_text.return_value = [0.1] * 384

        store = MemoryStore(
            jsonl_path=MagicMock(),
            db_conn=knowledge_db.connection,
            embedder=mock_embedder,
        )

        fact = _make_fact()
        store.write_fact(fact)

        # Verify fact exists
        fact_row = knowledge_db.connection.execute(
            "SELECT id::VARCHAR FROM memory_facts WHERE id = ?::UUID",
            [fact.id],
        ).fetchone()
        assert fact_row is not None

        # Verify embedding exists
        embed_row = knowledge_db.connection.execute(
            "SELECT id::VARCHAR FROM memory_embeddings WHERE id = ?::UUID",
            [fact.id],
        ).fetchone()
        assert embed_row is not None


# ---------------------------------------------------------------------------
# TS-52-13: Causal link idempotent insertion
# ---------------------------------------------------------------------------


class TestCausalLinkIdempotent:
    """TS-52-13: Inserting the same causal link twice results in one row.

    Requirement: 52-REQ-7.1
    """

    def test_duplicate_link_produces_one_row(self, knowledge_db: KnowledgeDB) -> None:
        """INSERT OR IGNORE should silently skip duplicate links."""
        fact_a = _make_fact(content="Cause fact")
        fact_b = _make_fact(content="Effect fact")
        sync_facts_to_duckdb(knowledge_db, [fact_a, fact_b])

        conn = knowledge_db.connection
        store_causal_links(conn, [(fact_a.id, fact_b.id)])
        store_causal_links(conn, [(fact_a.id, fact_b.id)])

        count = conn.execute(
            "SELECT COUNT(*) FROM fact_causes "
            "WHERE cause_id = ?::UUID AND effect_id = ?::UUID",
            [fact_a.id, fact_b.id],
        ).fetchone()[0]
        assert count == 1


# ---------------------------------------------------------------------------
# TS-52-E4: Missing fact in causal link
# ---------------------------------------------------------------------------


class TestMissingFactLinkSkipped:
    """TS-52-E4: Causal links referencing non-existent facts are skipped.

    Requirement: 52-REQ-7.E1
    """

    def test_link_with_nonexistent_fact_skipped(
        self, knowledge_db: KnowledgeDB
    ) -> None:
        """Links referencing non-existent facts should not be inserted."""
        existing_fact = _make_fact(content="I exist")
        sync_facts_to_duckdb(knowledge_db, [existing_fact])

        nonexistent_id = str(uuid.uuid4())
        conn = knowledge_db.connection

        stored = store_causal_links(conn, [(existing_fact.id, nonexistent_id)])
        assert stored == 0

        count = conn.execute("SELECT COUNT(*) FROM fact_causes").fetchone()[0]
        assert count == 0

    def test_link_with_both_nonexistent_skipped(
        self, knowledge_db: KnowledgeDB
    ) -> None:
        """Links where both facts are missing should not be inserted."""
        id_a = str(uuid.uuid4())
        id_b = str(uuid.uuid4())
        conn = knowledge_db.connection

        stored = store_causal_links(conn, [(id_a, id_b)])
        assert stored == 0
