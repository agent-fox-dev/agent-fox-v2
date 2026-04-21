"""Tests for cold-start detection and skip in AdaptiveRetriever.

Suite 6: Cold-Start Detection (TS-6.1 through TS-6.4)

Requirements: 113-REQ-6.1, 113-REQ-6.2, 113-REQ-6.E1
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import duckdb
import pytest

from agent_fox.core.config import RetrievalConfig
from agent_fox.knowledge.retrieval import AdaptiveRetriever


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


@pytest.fixture
def retrieval_config() -> RetrievalConfig:
    """A minimal retrieval config for testing."""
    return RetrievalConfig()


def _make_retriever(conn: duckdb.DuckDBPyConnection) -> AdaptiveRetriever:
    """Create an AdaptiveRetriever with no embedder (to avoid vector signal)."""
    config = RetrievalConfig()
    return AdaptiveRetriever(conn, config, embedder=None)


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    *,
    spec_name: str = "test_spec",
    confidence: float = 0.9,
    content: str | None = None,
    superseded_by: str | None = None,
) -> str:
    """Insert a fact into memory_facts and return its UUID."""
    fact_id = str(uuid.uuid4())
    fact_content = content or f"A test fact about {spec_name} with sufficient detail"
    conn.execute(
        """
        INSERT INTO memory_facts (id, content, category, spec_name, confidence, created_at, superseded_by)
        VALUES (?::UUID, ?, 'decision', ?, ?, CURRENT_TIMESTAMP, ?::UUID)
        """,
        [fact_id, fact_content, spec_name, confidence, superseded_by],
    )
    return fact_id


# ---------------------------------------------------------------------------
# TS-6.1: Cold-start returns empty result
# ---------------------------------------------------------------------------


class TestColdStartReturnsEmptyResult:
    """TS-6.1: Empty memory_facts → cold_start=True, no signals run."""

    def test_cold_start_flag_set_on_empty_db(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-6.1: RetrievalResult.cold_start == True when no facts exist."""
        retriever = _make_retriever(knowledge_conn_with_schema)

        result = retriever.retrieve(
            spec_name="new_spec",
            archetype="coder",
            node_status="fresh",
            touched_files=[],
            task_description="implement feature X",
        )

        # cold_start field must exist and be True
        assert hasattr(result, "cold_start"), (
            "RetrievalResult must have a cold_start field (113-REQ-6.2)"
        )
        assert result.cold_start is True, (
            "cold_start should be True when no facts exist"
        )

    def test_cold_start_context_is_empty(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-6.1: context is empty or minimal when cold_start=True."""
        retriever = _make_retriever(knowledge_conn_with_schema)

        result = retriever.retrieve(
            spec_name="new_spec",
            archetype="coder",
            node_status="fresh",
            touched_files=[],
            task_description="implement feature X",
        )

        # Context should be empty or just the section header
        assert result.context.strip() in ("", "## Knowledge Context"), (
            f"Expected empty context on cold start, got: {result.context!r}"
        )

    def test_cold_start_signal_counts_empty(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-6.1: signal_counts is empty on cold start."""
        retriever = _make_retriever(knowledge_conn_with_schema)

        result = retriever.retrieve(
            spec_name="new_spec",
            archetype="coder",
            node_status="fresh",
            touched_files=[],
            task_description="implement feature X",
        )

        # Signal counts should be empty (no signals ran)
        assert all(count == 0 for count in result.signal_counts.values()), (
            f"Expected empty signal counts on cold start, got: {result.signal_counts}"
        )

    def test_cold_start_debug_log_message(
        self,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """TS-6.1: Debug log contains 'Skipping retrieval: no facts available (cold start)'."""
        import logging

        retriever = _make_retriever(knowledge_conn_with_schema)

        with caplog.at_level(logging.DEBUG, logger="agent_fox.knowledge.retrieval"):
            retriever.retrieve(
                spec_name="new_spec",
                archetype="coder",
                node_status="fresh",
                touched_files=[],
                task_description="implement feature X",
            )

        log_messages = [r.message for r in caplog.records]
        assert any(
            "cold start" in msg.lower() or "Skipping retrieval" in msg
            for msg in log_messages
        ), f"Expected cold-start debug message. Got: {log_messages}"


# ---------------------------------------------------------------------------
# TS-6.2: Non-cold-start proceeds normally
# ---------------------------------------------------------------------------


class TestNonColdStartProceeds:
    """TS-6.2: When facts exist, cold_start=False and signals run."""

    def test_cold_start_false_when_facts_exist(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-6.2: cold_start=False when 5 facts exist for the spec."""
        conn = knowledge_conn_with_schema
        for i in range(5):
            _insert_fact(conn, spec_name="existing_spec", confidence=0.9)

        retriever = _make_retriever(conn)

        result = retriever.retrieve(
            spec_name="existing_spec",
            archetype="coder",
            node_status="fresh",
            touched_files=[],
            task_description="implement feature X",
        )

        assert hasattr(result, "cold_start"), "RetrievalResult must have cold_start field"
        assert result.cold_start is False

    def test_signal_counts_non_empty_when_facts_exist(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-6.2: At least one signal has non-zero count when facts exist."""
        conn = knowledge_conn_with_schema
        for i in range(5):
            _insert_fact(conn, spec_name="existing_spec", confidence=0.9)

        retriever = _make_retriever(conn)

        result = retriever.retrieve(
            spec_name="existing_spec",
            archetype="coder",
            node_status="fresh",
            touched_files=[],
            task_description="feature implementation",
            keywords=["existing", "spec"],
        )

        assert any(count > 0 for count in result.signal_counts.values()), (
            f"Expected at least one non-zero signal count, got: {result.signal_counts}"
        )


# ---------------------------------------------------------------------------
# TS-6.3: Count query failure falls through
# ---------------------------------------------------------------------------


class TestCountQueryFailureFallsThrough:
    """TS-6.3: If count query fails, proceed with normal retrieval (not cold start)."""

    def test_db_error_on_count_falls_through_to_normal_retrieval(
        self,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """TS-6.3: On count query failure, warning logged and retrieval proceeds.

        Requirements: 113-REQ-6.E1
        """
        import logging

        conn = knowledge_conn_with_schema
        retriever = _make_retriever(conn)

        # Patch _count_available_facts to simulate a database error
        with (
            patch.object(
                retriever,
                "_count_available_facts",
                side_effect=duckdb.Error("Simulated DB error"),
            ),
            caplog.at_level(logging.WARNING, logger="agent_fox.knowledge.retrieval"),
        ):
            result = retriever.retrieve(
                spec_name="any_spec",
                archetype="coder",
                node_status="fresh",
                touched_files=[],
                task_description="test",
            )

        # Should proceed with normal retrieval (not cold start)
        assert result.cold_start is False, (
            "cold_start should be False when count query fails (fall through to normal)"
        )
        # Warning should be logged
        assert any(
            "warning" in r.levelname.lower() or "count" in r.message.lower()
            for r in caplog.records
        ), f"Expected warning log for count query failure. Got: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# TS-6.4: Global high-confidence facts prevent cold start
# ---------------------------------------------------------------------------


class TestGlobalHighConfidenceFactsPreventColdStart:
    """TS-6.4: High-confidence facts from another spec prevent cold start."""

    def test_high_confidence_global_facts_trigger_retrieval(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-6.4: cold_start=False when global facts exceed the confidence threshold.

        Requirements: 113-REQ-6.1
        """
        conn = knowledge_conn_with_schema
        # No facts for "new_spec"
        # But 3 high-confidence facts for "other_spec"
        for _ in range(3):
            _insert_fact(conn, spec_name="other_spec", confidence=0.9)

        retriever = _make_retriever(conn)

        result = retriever.retrieve(
            spec_name="new_spec",
            archetype="coder",
            node_status="fresh",
            touched_files=[],
            task_description="implement new feature",
            confidence_threshold=0.5,
        )

        # High-confidence global facts (0.9 >= 0.5 threshold) prevent cold start
        assert result.cold_start is False, (
            "cold_start should be False because high-confidence global facts exist"
        )


# ---------------------------------------------------------------------------
# TS-6.x: _count_available_facts unit tests
# ---------------------------------------------------------------------------


class TestCountAvailableFacts:
    """Unit tests for AdaptiveRetriever._count_available_facts."""

    def test_count_zero_on_empty_db(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """_count_available_facts returns 0 when DB is empty."""
        retriever = _make_retriever(knowledge_conn_with_schema)
        count = retriever._count_available_facts("any_spec", confidence_threshold=0.5)
        assert count == 0

    def test_count_reflects_spec_name_match(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """_count_available_facts counts facts matching spec_name."""
        conn = knowledge_conn_with_schema
        _insert_fact(conn, spec_name="target_spec", confidence=0.3)
        _insert_fact(conn, spec_name="other_spec", confidence=0.3)

        retriever = _make_retriever(conn)
        # Only target_spec facts, threshold=0.5 (so other_spec won't qualify by confidence)
        count = retriever._count_available_facts("target_spec", confidence_threshold=0.5)
        assert count >= 1, "Should count at least the target_spec fact"

    def test_count_reflects_high_confidence_global_facts(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """_count_available_facts counts global high-confidence facts."""
        conn = knowledge_conn_with_schema
        _insert_fact(conn, spec_name="global_spec", confidence=0.9)

        retriever = _make_retriever(conn)
        count = retriever._count_available_facts("new_spec", confidence_threshold=0.5)
        # The global fact (confidence=0.9 >= 0.5) should be counted
        assert count >= 1

    def test_count_excludes_superseded_facts(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """_count_available_facts excludes superseded facts."""
        conn = knowledge_conn_with_schema
        survivor_id = _insert_fact(conn, spec_name="spec1", confidence=0.9)
        # superseded fact
        _insert_fact(conn, spec_name="spec1", confidence=0.9, superseded_by=survivor_id)

        retriever = _make_retriever(conn)
        count = retriever._count_available_facts("spec1", confidence_threshold=0.5)
        assert count == 1, "Should not count superseded facts"

    def test_count_returns_none_on_db_error(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """_count_available_facts returns None on database error (for caller to fall through)."""
        retriever = _make_retriever(knowledge_conn_with_schema)

        # Mock the connection to raise an error
        with patch.object(
            retriever._conn,
            "execute",
            side_effect=duckdb.Error("Simulated DB error"),
        ):
            count = retriever._count_available_facts("any_spec", confidence_threshold=0.5)

        assert count is None, (
            "_count_available_facts should return None on database error "
            "so callers can distinguish failure from genuine zero"
        )
