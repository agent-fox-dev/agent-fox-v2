"""Unit tests for run_id wiring in FoxKnowledgeProvider.

Tests verify that set_run_id() stores the run ID and that summary
queries use it to filter results. When run_id is not set (or set to
empty string), summary queries return empty lists.

Test Spec: TS-120-1, TS-120-2, TS-120-3, TS-120-E1, TS-120-E2
Requirements: 120-REQ-1.1, 120-REQ-1.2, 120-REQ-1.4, 120-REQ-1.5,
              120-REQ-1.E1, 120-REQ-1.E2
"""

from __future__ import annotations

import uuid

import duckdb
import pytest

from agent_fox.core.config import KnowledgeProviderConfig
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
from agent_fox.knowledge.migrations import run_migrations
from agent_fox.knowledge.summary_store import SummaryRecord, insert_summary

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def provider_conn() -> duckdb.DuckDBPyConnection:
    """DuckDB with full migrated schema for provider tests."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture()
def provider_db(provider_conn: duckdb.DuckDBPyConnection) -> KnowledgeDB:
    """KnowledgeDB wrapper around provider_conn."""
    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = provider_conn
    return db


def _make_provider(provider_db: KnowledgeDB, run_id: str | None = None) -> FoxKnowledgeProvider:
    """Construct FoxKnowledgeProvider, optionally setting run_id."""
    provider = FoxKnowledgeProvider(provider_db, KnowledgeProviderConfig())
    if run_id is not None:
        provider.set_run_id(run_id)
    return provider


def _make_summary(
    *,
    spec_name: str = "test_spec",
    task_group: str = "1",
    run_id: str = "run1",
    archetype: str = "coder",
    attempt: int = 1,
    summary: str = "Built module X",
) -> SummaryRecord:
    return SummaryRecord(
        id=str(uuid.uuid4()),
        node_id=f"{spec_name}:{task_group}",
        run_id=run_id,
        spec_name=spec_name,
        task_group=task_group,
        archetype=archetype,
        attempt=attempt,
        summary=summary,
        created_at="2026-04-29T10:00:00",
    )


# ---------------------------------------------------------------------------
# TS-120-1: set_run_id stores run ID (120-REQ-1.1)
# ---------------------------------------------------------------------------


class TestSetRunIdStoresRunId:
    """Verify that set_run_id() stores the run ID on the provider."""

    def test_stores_run_id(self, provider_db: KnowledgeDB) -> None:
        provider = FoxKnowledgeProvider(provider_db, KnowledgeProviderConfig())
        provider.set_run_id("20260429_081931_abc123")
        assert provider._run_id == "20260429_081931_abc123"


# ---------------------------------------------------------------------------
# TS-120-2: Summaries retrieved after set_run_id (120-REQ-1.2, 120-REQ-1.4)
# ---------------------------------------------------------------------------


class TestSummariesRetrievedAfterSetRunId:
    """Verify that same-spec summaries are returned when run_id is set."""

    def test_context_items_returned(
        self,
        provider_db: KnowledgeDB,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        insert_summary(
            provider_conn,
            _make_summary(
                spec_name="test_spec",
                task_group="1",
                run_id="run1",
                summary="Built module X",
            ),
        )
        provider = _make_provider(provider_db, run_id="run1")
        result = provider.retrieve("test_spec", "test", task_group="2")
        assert any("[CONTEXT]" in item and "Built module X" in item for item in result)


# ---------------------------------------------------------------------------
# TS-120-3: Cross-spec summaries retrieved after set_run_id (120-REQ-1.5)
# ---------------------------------------------------------------------------


class TestCrossSpecSummariesRetrieved:
    """Verify cross-spec summaries are returned when run_id is set."""

    def test_cross_spec_items_returned(
        self,
        provider_db: KnowledgeDB,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        insert_summary(
            provider_conn,
            _make_summary(
                spec_name="other_spec",
                task_group="1",
                run_id="run1",
                summary="Changed auth",
            ),
        )
        provider = _make_provider(provider_db, run_id="run1")
        result = provider.retrieve("test_spec", "test", task_group="1")
        assert any("[CROSS-SPEC]" in item and "Changed auth" in item for item in result)


# ---------------------------------------------------------------------------
# TS-120-E1: set_run_id never called — summaries return empty (120-REQ-1.E1)
# ---------------------------------------------------------------------------


class TestSetRunIdNeverCalled:
    """Summaries return empty when run_id is not set."""

    def test_no_context_items(
        self,
        provider_db: KnowledgeDB,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        insert_summary(
            provider_conn,
            _make_summary(spec_name="test_spec", task_group="1", run_id="run1"),
        )
        # Do NOT call set_run_id
        provider = FoxKnowledgeProvider(provider_db, KnowledgeProviderConfig())
        result = provider.retrieve("test_spec", "test", task_group="2")
        assert not any("[CONTEXT]" in item for item in result)
        assert not any("[CROSS-SPEC]" in item for item in result)


# ---------------------------------------------------------------------------
# TS-120-E2: set_run_id with empty string (120-REQ-1.E2)
# ---------------------------------------------------------------------------


class TestSetRunIdEmptyString:
    """Empty string treated as unset."""

    def test_empty_string_no_summaries(
        self,
        provider_db: KnowledgeDB,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        insert_summary(
            provider_conn,
            _make_summary(spec_name="test_spec", task_group="1", run_id="run1"),
        )
        provider = _make_provider(provider_db, run_id="")
        result = provider.retrieve("test_spec", "test", task_group="2")
        assert not any("[CONTEXT]" in item for item in result)
