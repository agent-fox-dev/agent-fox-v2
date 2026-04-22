"""Unit tests for gotcha extraction from session transcripts.

Test Spec: TS-115-4, TS-115-5, TS-115-6, TS-115-8, TS-115-E3, TS-115-E4
Requirements: 115-REQ-2.1, 115-REQ-2.2, 115-REQ-2.3, 115-REQ-2.5,
              115-REQ-2.E2, 115-REQ-2.E3
"""

from __future__ import annotations

import hashlib
import logging
from unittest.mock import patch

import duckdb
import pytest

from agent_fox.knowledge.gotcha_extraction import GotchaCandidate
from agent_fox.knowledge.migrations import apply_pending_migrations
from tests.unit.knowledge.conftest import SCHEMA_DDL

# ---------------------------------------------------------------------------
# DDL for gotchas table (matches migration v17 design)
# ---------------------------------------------------------------------------

_GOTCHAS_DDL = """
CREATE TABLE IF NOT EXISTS gotchas (
    id           VARCHAR PRIMARY KEY,
    spec_name    VARCHAR NOT NULL,
    category     VARCHAR NOT NULL DEFAULT 'gotcha',
    text         VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    session_id   VARCHAR NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def extraction_conn() -> duckdb.DuckDBPyConnection:
    """DuckDB with full schema + gotchas table for extraction tests."""
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL)
    apply_pending_migrations(conn)
    conn.execute(_GOTCHAS_DDL)
    yield conn
    conn.close()


@pytest.fixture()
def extraction_db(extraction_conn: duckdb.DuckDBPyConnection):
    """KnowledgeDB wrapper around extraction_conn."""
    from agent_fox.knowledge.db import KnowledgeDB

    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = extraction_conn
    return db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMPLETED_CONTEXT = {
    "session_status": "completed",
    "touched_files": ["src/f.py"],
    "commit_sha": "abc123",
}


def _make_candidate(text: str) -> GotchaCandidate:
    """Create a GotchaCandidate with computed content hash."""
    normalized = " ".join(text.lower().split())
    content_hash = hashlib.sha256(normalized.encode()).hexdigest()
    return GotchaCandidate(text=text, content_hash=content_hash)


# ===========================================================================
# TS-115-4: Gotcha Extraction on Ingest
# ===========================================================================


class TestGotchaExtraction:
    """Verify ingest() calls LLM for gotcha extraction and stores results.

    Requirements: 115-REQ-2.1
    """

    def test_extraction_stores_gotchas(
        self, extraction_db, extraction_conn
    ) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        mock_candidates = [
            _make_candidate("DuckDB ON CONFLICT requires explicit columns"),
            _make_candidate("Hypothesis deadline must be disabled for DB tests"),
        ]

        provider = FoxKnowledgeProvider(
            extraction_db, KnowledgeProviderConfig()
        )

        with patch(
            "agent_fox.knowledge.gotcha_extraction.extract_gotchas",
            return_value=mock_candidates,
        ):
            provider.ingest("session-1", "spec_01", _COMPLETED_CONTEXT)

        rows = extraction_conn.execute(
            "SELECT * FROM gotchas WHERE spec_name = 'spec_01'"
        ).fetchall()
        assert len(rows) == 2


# ===========================================================================
# TS-115-5: SIMPLE Model Tier for Extraction
# ===========================================================================


class TestModelTier:
    """Verify gotcha extraction uses the SIMPLE model tier.

    Requirements: 115-REQ-2.2
    """

    def test_simple_model_tier_used(self, extraction_db) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        provider = FoxKnowledgeProvider(
            extraction_db, KnowledgeProviderConfig(model_tier="SIMPLE")
        )

        with patch(
            "agent_fox.knowledge.gotcha_extraction.extract_gotchas",
            return_value=[],
        ) as mock_extract:
            provider.ingest("s1", "spec_01", _COMPLETED_CONTEXT)

            # Verify extract_gotchas was called with SIMPLE tier
            mock_extract.assert_called_once()
            call_args, call_kwargs = mock_extract.call_args
            # model_tier is the 2nd positional arg to extract_gotchas(context, model_tier)
            assert len(call_args) >= 2, "Expected at least 2 positional args"
            assert call_args[1] == "SIMPLE", f"Expected model_tier='SIMPLE', got {call_args[1]!r}"


# ===========================================================================
# TS-115-6: Zero Gotchas From LLM
# ===========================================================================


class TestZeroCandidates:
    """Verify no storage when LLM returns zero candidates.

    Requirements: 115-REQ-2.3
    """

    def test_zero_candidates_no_storage(
        self, extraction_db, extraction_conn
    ) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        provider = FoxKnowledgeProvider(
            extraction_db, KnowledgeProviderConfig()
        )

        with patch(
            "agent_fox.knowledge.gotcha_extraction.extract_gotchas",
            return_value=[],
        ):
            provider.ingest("s1", "spec_01", _COMPLETED_CONTEXT)

        rows = extraction_conn.execute(
            "SELECT * FROM gotchas"
        ).fetchall()
        assert len(rows) == 0


# ===========================================================================
# TS-115-8: Skip Ingest for Non-Completed Sessions
# ===========================================================================


class TestSkipNonCompleted:
    """Verify ingest() skips extraction when session_status is not 'completed'.

    Requirements: 115-REQ-2.5
    """

    def test_skip_failed_session(self, extraction_db, extraction_conn) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        provider = FoxKnowledgeProvider(
            extraction_db, KnowledgeProviderConfig()
        )

        with patch(
            "agent_fox.knowledge.gotcha_extraction.extract_gotchas",
        ) as mock_extract:
            provider.ingest(
                "s1",
                "spec_01",
                {
                    "session_status": "failed",
                    "touched_files": [],
                    "commit_sha": "",
                },
            )

            mock_extract.assert_not_called()

        rows = extraction_conn.execute(
            "SELECT * FROM gotchas"
        ).fetchall()
        assert len(rows) == 0


# ===========================================================================
# TS-115-E3: LLM Extraction Failure
# ===========================================================================


class TestLLMFailure:
    """Verify LLM failure is logged and no gotchas are stored.

    Requirements: 115-REQ-2.E2
    """

    def test_llm_failure_logged(
        self, extraction_db, extraction_conn, caplog
    ) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        provider = FoxKnowledgeProvider(
            extraction_db, KnowledgeProviderConfig()
        )

        with patch(
            "agent_fox.knowledge.gotcha_extraction.extract_gotchas",
            side_effect=RuntimeError("LLM failed"),
        ):
            with caplog.at_level(logging.WARNING):
                # Should not raise
                provider.ingest("s1", "spec_01", _COMPLETED_CONTEXT)

        rows = extraction_conn.execute(
            "SELECT * FROM gotchas"
        ).fetchall()
        assert len(rows) == 0
        assert any(r.levelno >= logging.WARNING for r in caplog.records), (
            "Expected at least one WARNING-level log record"
        )


# ===========================================================================
# TS-115-E4: LLM Returns More Than 3
# ===========================================================================


class TestCapAtThree:
    """Verify only first 3 gotchas stored when LLM returns more.

    Requirements: 115-REQ-2.E3
    """

    def test_cap_at_three(self, extraction_db, extraction_conn) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        mock_candidates = [_make_candidate(f"Gotcha {i}") for i in range(5)]

        provider = FoxKnowledgeProvider(
            extraction_db, KnowledgeProviderConfig()
        )

        with patch(
            "agent_fox.knowledge.gotcha_extraction.extract_gotchas",
            return_value=mock_candidates,
        ):
            provider.ingest("s1", "spec_01", _COMPLETED_CONTEXT)

        rows = extraction_conn.execute(
            "SELECT * FROM gotchas WHERE spec_name = 'spec_01'"
        ).fetchall()
        assert len(rows) == 3
