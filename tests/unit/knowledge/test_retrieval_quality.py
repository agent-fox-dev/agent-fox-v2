"""Tests for retrieval quality validation: audit events and session outcome summary.

Suite 7: Retrieval Quality Validation (TS-7.1 through TS-7.3)

Requirements: 113-REQ-7.1, 113-REQ-7.2, 113-REQ-7.E1
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import duckdb
import pytest

from agent_fox.core.config import RetrievalConfig
from agent_fox.knowledge.retrieval import AdaptiveRetriever, RetrievalResult


@pytest.fixture
def knowledge_conn_with_schema():
    """In-memory DuckDB with full production schema."""
    from agent_fox.knowledge.migrations import run_migrations

    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    *,
    spec_name: str = "05_foo",
    confidence: float = 0.9,
    keywords: list[str] | None = None,
) -> str:
    """Insert a fact and return its UUID."""
    fact_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO memory_facts (id, content, category, spec_name, confidence, keywords, created_at)
        VALUES (?::UUID, ?, 'decision', ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        [fact_id, f"A detailed fact about {spec_name} that is very relevant", spec_name, confidence,
         keywords or ["test"]],
    )
    return fact_id


def _make_retriever(conn: duckdb.DuckDBPyConnection) -> AdaptiveRetriever:
    """Create a retriever with no embedder."""
    return AdaptiveRetriever(conn, RetrievalConfig(), embedder=None)


# ---------------------------------------------------------------------------
# TS-7.1: Retrieval audit event emitted
# ---------------------------------------------------------------------------


class TestRetrievalAuditEventEmitted:
    """TS-7.1: knowledge.retrieval audit event emitted after non-empty retrieval."""

    def test_knowledge_retrieval_event_type_exists(self) -> None:
        """TS-7.1: AuditEventType.KNOWLEDGE_RETRIEVAL exists.

        Requirements: 113-REQ-7.1
        """
        from agent_fox.knowledge.audit import AuditEventType

        assert hasattr(AuditEventType, "KNOWLEDGE_RETRIEVAL"), (
            "AuditEventType.KNOWLEDGE_RETRIEVAL must be added (113-REQ-7.1)"
        )
        assert AuditEventType.KNOWLEDGE_RETRIEVAL == "knowledge.retrieval"

    def test_retrieval_audit_event_emitted_with_correct_fields(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-7.1: Exactly one knowledge.retrieval event emitted after retrieval.

        Requirements: 113-REQ-7.1
        """
        conn = knowledge_conn_with_schema
        # Insert facts so retrieval is non-empty
        for _ in range(5):
            _insert_fact(conn, spec_name="05_foo")

        emitted_events: list[MagicMock] = []
        mock_sink = MagicMock()
        mock_sink.emit_audit_event.side_effect = emitted_events.append

        retriever = _make_retriever(conn)
        retriever._sink_dispatcher = mock_sink
        retriever._node_id = "05_foo:1"

        retriever.retrieve(
            spec_name="05_foo",
            archetype="coder",
            node_status="fresh",
            touched_files=[],
            task_description="implement feature X",
            keywords=["05_foo", "feature"],
        )

        # Filter for knowledge.retrieval events
        from agent_fox.knowledge.audit import AuditEventType

        knowledge_events = [
            e
            for e in emitted_events
            if hasattr(e, "event_type")
            and e.event_type == AuditEventType.KNOWLEDGE_RETRIEVAL
        ]
        assert len(knowledge_events) == 1, (
            f"Expected exactly 1 knowledge.retrieval event, got {len(knowledge_events)}"
        )

    def test_audit_event_payload_has_required_fields(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-7.1: Event payload contains spec_name, node_id, facts_returned,
        signals_active, cold_start, token_budget_used.
        """
        conn = knowledge_conn_with_schema
        for _ in range(5):
            _insert_fact(conn, spec_name="05_foo")

        captured_event = None

        def capture_event(event):
            nonlocal captured_event
            from agent_fox.knowledge.audit import AuditEventType

            if hasattr(event, "event_type") and event.event_type == AuditEventType.KNOWLEDGE_RETRIEVAL:
                captured_event = event

        mock_sink = MagicMock()
        mock_sink.emit_audit_event.side_effect = capture_event

        retriever = _make_retriever(conn)
        retriever._sink_dispatcher = mock_sink
        retriever._node_id = "05_foo:1"

        retriever.retrieve(
            spec_name="05_foo",
            archetype="coder",
            node_status="fresh",
            touched_files=[],
            task_description="implement feature X",
            keywords=["05_foo"],
        )

        assert captured_event is not None, "No knowledge.retrieval event was captured"
        payload = captured_event.payload
        assert "spec_name" in payload, "payload missing spec_name"
        assert "node_id" in payload, "payload missing node_id"
        assert "facts_returned" in payload, "payload missing facts_returned"
        assert "signals_active" in payload, "payload missing signals_active"
        assert "cold_start" in payload, "payload missing cold_start"
        assert "token_budget_used" in payload, "payload missing token_budget_used"

        assert payload["spec_name"] == "05_foo"
        assert payload["node_id"] == "05_foo:1"
        assert isinstance(payload["facts_returned"], int)
        assert isinstance(payload["signals_active"], list)
        assert isinstance(payload["cold_start"], bool)
        assert isinstance(payload["token_budget_used"], int)
        assert payload["token_budget_used"] >= 0


# ---------------------------------------------------------------------------
# TS-7.2: Retrieval summary stored in session outcomes
# ---------------------------------------------------------------------------


class TestRetrievalSummaryInSessionOutcomes:
    """TS-7.2: retrieval_summary stored in session_outcomes after retrieval."""

    def test_retrieval_result_has_token_budget_used_field(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-7.2: RetrievalResult.token_budget_used field exists.

        Requirements: 113-REQ-7.2
        """
        conn = knowledge_conn_with_schema
        for _ in range(3):
            _insert_fact(conn, spec_name="test_spec")

        retriever = _make_retriever(conn)
        result = retriever.retrieve(
            spec_name="test_spec",
            archetype="coder",
            node_status="fresh",
            touched_files=[],
            task_description="test",
        )

        assert hasattr(result, "token_budget_used"), (
            "RetrievalResult must have token_budget_used field (113-REQ-7.2)"
        )
        assert isinstance(result.token_budget_used, int)

    def test_session_outcomes_has_retrieval_summary_column(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-7.2: session_outcomes table has retrieval_summary column."""
        conn = knowledge_conn_with_schema

        # Check that the column exists via DESCRIBE
        cols = conn.execute("DESCRIBE session_outcomes").fetchall()
        col_names = [c[0] for c in cols]

        assert "retrieval_summary" in col_names, (
            "session_outcomes table must have a retrieval_summary column (113-REQ-7.2)"
        )


# ---------------------------------------------------------------------------
# TS-7.3: Audit event failure does not block session
# ---------------------------------------------------------------------------


class TestAuditEventFailureDoesNotBlock:
    """TS-7.3: If audit event emission fails, retrieval still returns valid result."""

    def test_retrieval_proceeds_when_emit_fails(
        self,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """TS-7.3: emit_audit_event failure → valid RetrievalResult, warning logged.

        Requirements: 113-REQ-7.E1
        """
        import logging

        conn = knowledge_conn_with_schema
        for _ in range(3):
            _insert_fact(conn, spec_name="05_foo")

        mock_sink = MagicMock()
        mock_sink.emit_audit_event.side_effect = RuntimeError("Sink failure")

        retriever = _make_retriever(conn)
        retriever._sink_dispatcher = mock_sink
        retriever._node_id = "05_foo:1"

        with caplog.at_level(logging.WARNING, logger="agent_fox.knowledge.retrieval"):
            result = retriever.retrieve(
                spec_name="05_foo",
                archetype="coder",
                node_status="fresh",
                touched_files=[],
                task_description="implement feature X",
                keywords=["05_foo"],
            )

        # Retrieval must succeed even if audit event fails
        assert isinstance(result, RetrievalResult), (
            "retrieve() must return a valid RetrievalResult even when audit event fails"
        )
        assert result is not None

        # Warning should be logged
        warning_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert any("audit" in msg.lower() or "emit" in msg.lower() or "event" in msg.lower()
                   for msg in warning_messages), (
            f"Expected warning about audit event failure. Got warnings: {warning_messages}"
        )
