"""Unit tests for FoxKnowledgeProvider session summary formatting.

Test Spec: TS-119-6, TS-119-12
Requirements: 119-REQ-2.2, 119-REQ-3.2
"""

from __future__ import annotations

import uuid

import duckdb
import pytest

from agent_fox.knowledge.migrations import run_migrations
from agent_fox.knowledge.summary_store import (
    SummaryRecord,
    insert_summary,
)

_SESSION_SUMMARIES_DDL = """
CREATE TABLE IF NOT EXISTS session_summaries (
    id          UUID PRIMARY KEY,
    node_id     VARCHAR NOT NULL,
    run_id      VARCHAR NOT NULL,
    spec_name   VARCHAR NOT NULL,
    task_group  VARCHAR NOT NULL,
    archetype   VARCHAR NOT NULL,
    attempt     INTEGER NOT NULL DEFAULT 1,
    summary     TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL
);
"""


@pytest.fixture()
def provider_conn():
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    conn.execute(_SESSION_SUMMARIES_DDL)
    yield conn
    conn.close()


@pytest.fixture()
def provider_db(provider_conn):
    from agent_fox.knowledge.db import KnowledgeDB
    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = provider_conn
    return db


def _make_record(*, id=None, node_id="spec_a:2", run_id="run-1",
                 spec_name="spec_a", task_group="2", archetype="coder",
                 attempt=1, summary="Built the store",
                 created_at="2026-04-28T18:00:00"):
    return SummaryRecord(
        id=id or str(uuid.uuid4()), node_id=node_id, run_id=run_id,
        spec_name=spec_name, task_group=task_group, archetype=archetype,
        attempt=attempt, summary=summary, created_at=created_at,
    )


def _make_provider(provider_db, run_id=None):
    from agent_fox.core.config import KnowledgeProviderConfig
    from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

    provider = FoxKnowledgeProvider(provider_db, KnowledgeProviderConfig())
    # Set run_id so summary queries can filter by run.
    # The production code will receive run_id via constructor or config
    # (task 3.3); we set the private attribute to anticipate that wiring.
    if run_id is not None:
        provider._run_id = run_id
    return provider


# TS-119-6: Summaries formatted with CONTEXT prefix (119-REQ-2.2)
class TestSummariesFormattedWithContextPrefix:
    def test_context_prefix_format(self, provider_db, provider_conn):
        insert_summary(provider_conn, _make_record(
            spec_name="spec_a", task_group="2", node_id="spec_a:2",
            attempt=1, summary="Built the SQLite store with WAL mode",
        ))
        provider = _make_provider(provider_db, run_id="run-1")
        items = provider.retrieve("spec_a", "task description",
                                  task_group="3", session_id="spec_a:3")
        context_items = [i for i in items if i.startswith("[CONTEXT]")]
        assert len(context_items) >= 1
        assert "(coder, group 2, attempt 1)" in context_items[0]
        assert "Built the SQLite store with WAL mode" in context_items[0]


# TS-119-12: Cross-spec formatted with CROSS-SPEC prefix (119-REQ-3.2)
class TestCrossSpecFormattedWithPrefix:
    def test_cross_spec_prefix_format(self, provider_db, provider_conn):
        insert_summary(provider_conn, _make_record(
            spec_name="spec_b", task_group="3", node_id="spec_b:3",
            summary="Changed AuthConfig to remove BearerToken",
        ))
        provider = _make_provider(provider_db, run_id="run-1")
        items = provider.retrieve("spec_a", "task description",
                                  task_group="2", session_id="spec_a:2")
        cross_items = [i for i in items if i.startswith("[CROSS-SPEC]")]
        assert len(cross_items) >= 1
        assert "(spec_b, group 3)" in cross_items[0]
        assert "Changed AuthConfig to remove BearerToken" in cross_items[0]
