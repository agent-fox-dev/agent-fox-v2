"""Tests for errata generation when reviewer blocking occurs.

Verifies that SessionResultHandler._generate_errata is called when
check_skeptic_blocking returns True, and that errata are stored in
DuckDB and written to markdown.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from agent_fox.engine.result_handler import SessionResultHandler
from agent_fox.engine.state import ExecutionState, SessionRecord


@dataclass(frozen=True)
class FakeBlockDecision:
    should_block: bool
    coder_node_id: str = ""
    reason: str = ""


def _make_state() -> ExecutionState:
    return ExecutionState(plan_hash="test-hash", node_states={})


def _make_handler(*, knowledge_db_conn: Any = None) -> SessionResultHandler:
    """Create a minimal SessionResultHandler for testing."""
    graph_sync = MagicMock()
    graph_sync.node_states = {}
    graph_sync.predecessors.return_value = []

    return SessionResultHandler(
        graph_sync=graph_sync,
        routing_ladders={},
        retries_before_escalation=2,
        max_retries=3,
        task_callback=None,
        sink=MagicMock(),
        run_id="test-run-1",
        graph=None,
        archetypes_config=None,
        knowledge_db_conn=knowledge_db_conn,
        block_task_fn=MagicMock(),
        check_block_budget_fn=MagicMock(),
    )


def _make_record(
    node_id: str = "spec_42:1:reviewer:pre-review",
    status: str = "completed",
    archetype: str = "reviewer",
    attempt: int = 1,
) -> SessionRecord:
    return SessionRecord(
        node_id=node_id,
        attempt=attempt,
        status=status,
        input_tokens=100,
        output_tokens=200,
        cost=0.1,
        duration_ms=5000,
        error_message=None,
        timestamp="2026-04-23T12:00:00",
        archetype=archetype,
    )


def _setup_errata_db() -> duckdb.DuckDBPyConnection:
    """Create in-memory DB with review_findings and errata tables."""
    from agent_fox.knowledge.migrations import run_migrations

    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    return conn


class TestGenerateErrataOnBlocking:
    def test_errata_generated_when_blocking_occurs(self) -> None:
        conn = _setup_errata_db()

        finding_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO review_findings "
            "(id, severity, description, requirement_ref, spec_name, task_group, session_id) "
            "VALUES (?, 'critical', 'Auth bypass', 'REQ-1.1', 'spec_42', '1', 'spec_42:1:reviewer:pre-review:1')",
            [finding_id],
        )

        handler = _make_handler(knowledge_db_conn=conn)

        record = _make_record()
        with (
            patch(
                "agent_fox.engine.result_handler.evaluate_review_blocking",
                return_value=FakeBlockDecision(
                    should_block=True,
                    coder_node_id="spec_42:1",
                    reason="blocking",
                ),
            ),
            patch("agent_fox.knowledge.errata.persist_erratum_markdown", return_value=None),
        ):
            state = _make_state()
            handler.check_skeptic_blocking(record, state)

        rows = conn.execute("SELECT COUNT(*) FROM errata WHERE spec_name = 'spec_42'").fetchone()
        assert rows is not None and rows[0] >= 1

        conn.close()

    def test_no_errata_when_not_blocking(self) -> None:
        conn = _setup_errata_db()

        handler = _make_handler(knowledge_db_conn=conn)
        record = _make_record()

        with patch(
            "agent_fox.engine.result_handler.evaluate_review_blocking",
            return_value=FakeBlockDecision(should_block=False),
        ):
            state = _make_state()
            result = handler.check_skeptic_blocking(record, state)

        assert result is False
        rows = conn.execute("SELECT COUNT(*) FROM errata").fetchone()
        assert rows is not None and rows[0] == 0

        conn.close()

    def test_errata_generation_failure_does_not_propagate(self) -> None:
        handler = _make_handler(knowledge_db_conn=None)
        record = _make_record()

        with patch(
            "agent_fox.engine.result_handler.evaluate_review_blocking",
            return_value=FakeBlockDecision(
                should_block=True,
                coder_node_id="spec_42:1",
                reason="blocking",
            ),
        ):
            state = _make_state()
            result = handler.check_skeptic_blocking(record, state)

        assert result is True

    def test_errata_only_for_critical_major(self) -> None:
        conn = _setup_errata_db()

        f1_id = str(uuid.uuid4())
        f2_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO review_findings "
            "(id, severity, description, spec_name, task_group, session_id) "
            "VALUES (?, 'critical', 'Problem', 'spec_42', '1', 'spec_42:1:reviewer:pre-review:1'), "
            "       (?, 'minor', 'Style', 'spec_42', '1', 'spec_42:1:reviewer:pre-review:1')",
            [f1_id, f2_id],
        )

        handler = _make_handler(knowledge_db_conn=conn)
        record = _make_record()

        with (
            patch(
                "agent_fox.engine.result_handler.evaluate_review_blocking",
                return_value=FakeBlockDecision(
                    should_block=True,
                    coder_node_id="spec_42:1",
                    reason="blocking",
                ),
            ),
            patch("agent_fox.knowledge.errata.persist_erratum_markdown", return_value=None),
        ):
            state = _make_state()
            handler.check_skeptic_blocking(record, state)

        rows = conn.execute("SELECT COUNT(*) FROM errata WHERE spec_name = 'spec_42'").fetchone()
        assert rows is not None and rows[0] == 1

        row = conn.execute("SELECT finding_summary FROM errata WHERE spec_name = 'spec_42'").fetchone()
        assert row is not None
        assert "[critical]" in row[0]

        conn.close()


class TestErrataInFoxProvider:
    def test_retrieve_includes_errata(self) -> None:
        conn = _setup_errata_db()

        conn.execute(
            "INSERT INTO errata (id, spec_name, task_group, finding_summary) "
            "VALUES ('e1-uuid-placeholder', 'spec_42', '1', '[critical] Auth bypass')"
        )

        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        knowledge_db = MagicMock()
        knowledge_db.connection = conn
        config = KnowledgeProviderConfig()

        provider = FoxKnowledgeProvider(knowledge_db, config)
        result = provider.retrieve("spec_42", "task description")

        assert any("[ERRATA]" in item for item in result)
        assert any("Auth bypass" in item for item in result)

        conn.close()

    def test_retrieve_handles_missing_errata_table(self) -> None:
        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE review_findings (
                id UUID PRIMARY KEY,
                severity TEXT NOT NULL,
                description TEXT NOT NULL,
                requirement_ref TEXT,
                spec_name TEXT NOT NULL,
                task_group TEXT NOT NULL,
                session_id TEXT NOT NULL,
                superseded_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                category TEXT
            )
        """)

        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        knowledge_db = MagicMock()
        knowledge_db.connection = conn
        config = KnowledgeProviderConfig()

        provider = FoxKnowledgeProvider(knowledge_db, config)
        result = provider.retrieve("spec_42", "task description")
        assert isinstance(result, list)

        conn.close()
