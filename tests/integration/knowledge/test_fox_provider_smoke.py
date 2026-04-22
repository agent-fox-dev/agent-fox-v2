"""Integration smoke tests for FoxKnowledgeProvider.

Test Spec: TS-115-SMOKE-1 through TS-115-SMOKE-4
Requirements: 115-REQ-1.1, 115-REQ-2.1, 115-REQ-5.1, 115-REQ-5.4,
              115-REQ-10.1
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import duckdb
import pytest
from agent_fox.knowledge.errata_store import register_errata
from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
from agent_fox.knowledge.gotcha_extraction import GotchaCandidate

from agent_fox.core.config import KnowledgeProviderConfig
from agent_fox.knowledge.migrations import apply_pending_migrations
from agent_fox.knowledge.review_store import ReviewFinding, insert_findings
from tests.unit.knowledge.conftest import SCHEMA_DDL

# ---------------------------------------------------------------------------
# DDL for spec 115 tables
# ---------------------------------------------------------------------------

_SPEC_115_DDL = """
CREATE TABLE IF NOT EXISTS gotchas (
    id           VARCHAR PRIMARY KEY,
    spec_name    VARCHAR NOT NULL,
    category     VARCHAR NOT NULL DEFAULT 'gotcha',
    text         VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    session_id   VARCHAR NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS errata_index (
    spec_name  VARCHAR NOT NULL,
    file_path  VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (spec_name, file_path)
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def smoke_conn() -> duckdb.DuckDBPyConnection:
    """Full schema DuckDB for smoke tests."""
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL)
    apply_pending_migrations(conn)
    conn.execute(_SPEC_115_DDL)
    yield conn
    conn.close()


@pytest.fixture()
def smoke_db(smoke_conn):
    """KnowledgeDB wrapper for smoke tests."""
    from agent_fox.knowledge.db import KnowledgeDB

    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = smoke_conn
    return db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(text: str) -> GotchaCandidate:
    normalized = " ".join(text.lower().split())
    content_hash = hashlib.sha256(normalized.encode()).hexdigest()
    return GotchaCandidate(text=text, content_hash=content_hash)


def _insert_gotcha(conn, spec_name, text):
    normalized = " ".join(text.lower().split())
    content_hash = hashlib.sha256(normalized.encode()).hexdigest()
    conn.execute(
        "INSERT INTO gotchas (id, spec_name, category, text, content_hash, "
        "session_id, created_at) VALUES (?, ?, 'gotcha', ?, ?, ?, ?)",
        [str(uuid.uuid4()), spec_name, text, content_hash, "s1", datetime.now(UTC)],
    )


def _insert_review_finding(conn, spec_name, severity, description):
    finding = ReviewFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group="1",
        session_id="s1",
    )
    insert_findings(conn, [finding])


# ===========================================================================
# TS-115-SMOKE-1: Pre-Session Retrieval Path
# ===========================================================================


class TestPreSessionRetrievalSmoke:
    """Verify full retrieval path returns composed results from all three
    categories.

    Execution Path 1: retrieve() -> query_errata + query_active_findings
    + query_gotchas -> _compose_results.

    Must NOT satisfy with mocking FoxKnowledgeProvider, gotcha_store,
    errata_store, or review_store.
    """

    def test_retrieval_path(self, smoke_db, smoke_conn) -> None:
        # Seed: 1 errata, 1 critical finding, 2 gotchas
        register_errata(
            smoke_conn, "spec_01", "docs/errata/01_fix.md"
        )
        _insert_review_finding(
            smoke_conn, "spec_01", "critical", "SQL injection"
        )
        _insert_gotcha(smoke_conn, "spec_01", "DuckDB gotcha A")
        _insert_gotcha(smoke_conn, "spec_01", "DuckDB gotcha B")

        provider = FoxKnowledgeProvider(
            smoke_db, KnowledgeProviderConfig()
        )
        result = provider.retrieve("spec_01", "implement feature X")

        assert len(result) == 4
        assert result[0].startswith("[ERRATA]")
        assert result[1].startswith("[REVIEW]")
        assert result[2].startswith("[GOTCHA]")
        assert result[3].startswith("[GOTCHA]")


# ===========================================================================
# TS-115-SMOKE-2: Post-Session Ingestion Path
# ===========================================================================


class TestPostSessionIngestionSmoke:
    """Verify full ingestion path extracts gotchas via LLM and stores them.

    Execution Path 2: ingest() -> extract_gotchas (mocked LLM) ->
    store_gotchas.

    Must NOT satisfy with mocking FoxKnowledgeProvider or gotcha_store.
    Only the LLM call is mocked.
    """

    def test_ingestion_path(self, smoke_db, smoke_conn) -> None:
        mock_candidates = [
            _make_candidate("DuckDB ON CONFLICT requires explicit columns"),
            _make_candidate("Hypothesis deadline must be disabled"),
        ]

        provider = FoxKnowledgeProvider(
            smoke_db, KnowledgeProviderConfig()
        )

        with patch(
            "agent_fox.knowledge.gotcha_extraction.extract_gotchas",
            return_value=mock_candidates,
        ):
            provider.ingest(
                "session-1",
                "spec_01",
                {
                    "session_status": "completed",
                    "touched_files": ["f.py"],
                    "commit_sha": "abc",
                },
            )

        rows = smoke_conn.execute(
            "SELECT * FROM gotchas WHERE spec_name = 'spec_01'"
        ).fetchall()
        assert len(rows) == 2


# ===========================================================================
# TS-115-SMOKE-3: Errata Registration Path
# ===========================================================================


class TestErrataRegistrationSmoke:
    """Verify errata registration stores entry and retrieval returns it.

    Execution Path 3: register_errata -> DuckDB insert.

    Must NOT satisfy with mocking errata_store.
    """

    def test_errata_registration_path(self, smoke_db, smoke_conn) -> None:
        entry = register_errata(
            smoke_conn, "spec_28", "docs/errata/28_fix.md"
        )
        assert entry.spec_name == "spec_28"

        provider = FoxKnowledgeProvider(
            smoke_db, KnowledgeProviderConfig()
        )
        result = provider.retrieve("spec_28", "task")
        errata = [r for r in result if r.startswith("[ERRATA]")]

        assert len(errata) == 1
        assert "28_fix.md" in errata[0]


# ===========================================================================
# TS-115-SMOKE-4: Provider Construction at Startup
# ===========================================================================


class TestProviderConstructionSmoke:
    """Verify _setup_infrastructure constructs FoxKnowledgeProvider and
    wires it into the session runner factory.

    Execution Path 4: _setup_infrastructure -> FoxKnowledgeProvider(...)
    -> infrastructure dict.

    Must NOT satisfy with mocking _setup_infrastructure.
    """

    def test_provider_construction(self) -> None:
        from agent_fox.engine.run import _setup_infrastructure

        with (
            patch("agent_fox.engine.run.open_knowledge_store") as mock_store,
            patch("agent_fox.engine.run.DuckDBSink"),
            patch("agent_fox.engine.run.SinkDispatcher") as mock_sink_cls,
            patch("agent_fox.knowledge.agent_trace.AgentTraceSink"),
        ):
            mock_db = MagicMock()
            mock_db.connection = MagicMock()
            mock_store.return_value = mock_db
            mock_sink_cls.return_value = MagicMock()

            mock_config = MagicMock()
            mock_config.knowledge = MagicMock()

            infra = _setup_infrastructure(mock_config)

        assert isinstance(infra["knowledge_provider"], FoxKnowledgeProvider)
