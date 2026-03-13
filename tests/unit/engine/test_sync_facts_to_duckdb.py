"""Regression test: new facts are synced to DuckDB before causal link storage.

Verifies the fix for issue #83 — causal links referencing newly extracted
facts were skipped because the facts existed only in JSONL, not in DuckDB's
memory_facts table.
"""

from __future__ import annotations

import uuid

import pytest

from agent_fox.core.config import KnowledgeConfig
from agent_fox.engine.knowledge_harvest import sync_facts_to_duckdb
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.facts import Fact


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


@pytest.fixture
def knowledge_db(tmp_path: str) -> KnowledgeDB:
    config = KnowledgeConfig(store_path=":memory:")
    db = KnowledgeDB(config)
    db.open()
    return db


class TestSyncFactsToDuckDB:
    """Verify sync_facts_to_duckdb writes facts to memory_facts."""

    def test_facts_written_to_duckdb(self, knowledge_db: KnowledgeDB) -> None:
        fact = _make_fact()
        sync_facts_to_duckdb(knowledge_db, [fact])

        rows = knowledge_db.connection.execute(
            "SELECT id::VARCHAR FROM memory_facts WHERE id = ?::UUID",
            [fact.id],
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == fact.id

    def test_idempotent(self, knowledge_db: KnowledgeDB) -> None:
        fact = _make_fact()
        sync_facts_to_duckdb(knowledge_db, [fact])
        # Second call should not raise
        sync_facts_to_duckdb(knowledge_db, [fact])

        count = knowledge_db.connection.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE id = ?::UUID",
            [fact.id],
        ).fetchone()[0]
        assert count == 1

    def test_causal_links_succeed_after_sync(self, knowledge_db: KnowledgeDB) -> None:
        """End-to-end: after syncing, store_causal_links should find the facts."""
        from agent_fox.knowledge.causal import store_causal_links

        fact_a = _make_fact()
        fact_b = _make_fact()
        sync_facts_to_duckdb(knowledge_db, [fact_a, fact_b])

        inserted = store_causal_links(
            knowledge_db.connection,
            [(fact_a.id, fact_b.id)],
        )
        assert inserted == 1

    def test_prior_facts_synced_for_causal_links(
        self, knowledge_db: KnowledgeDB
    ) -> None:
        """Regression: prior facts from JSONL must be synced to DuckDB so
        causal links referencing them pass the referential integrity check.

        This was the real root cause of issue #83 — the original fix only
        synced new facts, but the LLM creates links between any facts
        (including old ones that only exist in JSONL).
        """
        from agent_fox.knowledge.causal import store_causal_links

        prior_fact = _make_fact()
        new_fact = _make_fact()

        # Simulate: prior_fact is only in JSONL (NOT in DuckDB)
        # new_fact is synced via sync_facts_to_duckdb
        sync_facts_to_duckdb(knowledge_db, [new_fact])

        # A causal link from prior -> new should FAIL because prior is missing
        inserted = store_causal_links(
            knowledge_db.connection,
            [(prior_fact.id, new_fact.id)],
        )
        assert inserted == 0, "Causal link should fail when prior fact is not in DuckDB"

        # Now sync BOTH facts (as the fix should do)
        sync_facts_to_duckdb(knowledge_db, [prior_fact, new_fact])

        # Now the link should succeed
        inserted = store_causal_links(
            knowledge_db.connection,
            [(prior_fact.id, new_fact.id)],
        )
        assert inserted == 1, "Causal link should succeed after syncing prior facts"
