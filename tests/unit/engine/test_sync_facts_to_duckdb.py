"""Regression test: new facts are synced to DuckDB before causal link storage.

Verifies the fix for issue #83 — causal links referencing newly extracted
facts were skipped because the facts existed only in JSONL, not in DuckDB's
memory_facts table.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from agent_fox.core.config import AgentFoxConfig, KnowledgeConfig, ModelConfig
from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.knowledge.db import KnowledgeDB
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


@pytest.fixture
def knowledge_db(tmp_path: str) -> KnowledgeDB:
    config = KnowledgeConfig(store_path=":memory:")
    db = KnowledgeDB(config)
    db.open()
    return db


@pytest.fixture
def lifecycle(knowledge_db: KnowledgeDB) -> NodeSessionRunner:
    config = MagicMock(spec=AgentFoxConfig)
    config.models = MagicMock(spec=ModelConfig)
    return NodeSessionRunner(
        node_id="test_spec:1",
        config=config,
        knowledge_db=knowledge_db,
    )


class TestSyncFactsToDuckDB:
    """Verify _sync_facts_to_duckdb writes facts to memory_facts."""

    def test_facts_written_to_duckdb(
        self, lifecycle: NodeSessionRunner, knowledge_db: KnowledgeDB
    ) -> None:
        fact = _make_fact()
        lifecycle._sync_facts_to_duckdb([fact])

        rows = knowledge_db.connection.execute(
            "SELECT id::VARCHAR FROM memory_facts WHERE id = ?::UUID",
            [fact.id],
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == fact.id

    def test_idempotent(
        self, lifecycle: NodeSessionRunner, knowledge_db: KnowledgeDB
    ) -> None:
        fact = _make_fact()
        lifecycle._sync_facts_to_duckdb([fact])
        # Second call should not raise
        lifecycle._sync_facts_to_duckdb([fact])

        count = knowledge_db.connection.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE id = ?::UUID",
            [fact.id],
        ).fetchone()[0]
        assert count == 1

    def test_causal_links_succeed_after_sync(
        self, lifecycle: NodeSessionRunner, knowledge_db: KnowledgeDB
    ) -> None:
        """End-to-end: after syncing, store_causal_links should find the facts."""
        from agent_fox.knowledge.causal import store_causal_links

        fact_a = _make_fact()
        fact_b = _make_fact()
        lifecycle._sync_facts_to_duckdb([fact_a, fact_b])

        inserted = store_causal_links(
            knowledge_db.connection,
            [(fact_a.id, fact_b.id)],
        )
        assert inserted == 1

    def test_no_knowledge_db_is_noop(self) -> None:
        config = MagicMock(spec=AgentFoxConfig)
        config.models = MagicMock(spec=ModelConfig)
        lc = NodeSessionRunner(
            node_id="test_spec:1",
            config=config,
            knowledge_db=None,
        )
        # Should not raise
        lc._sync_facts_to_duckdb([_make_fact()])
