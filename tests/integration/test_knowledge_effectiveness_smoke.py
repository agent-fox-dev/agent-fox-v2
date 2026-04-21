"""Integration smoke tests for knowledge system effectiveness (spec 113).

Tests each of the 7 execution paths from design.md using real DuckDB
connections and real module code. Only LLM calls are mocked.

Requirements: 113-REQ-1.* through 113-REQ-7.*
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest


@pytest.fixture
def knowledge_conn():
    """In-memory DuckDB with full production schema."""
    from agent_fox.knowledge.migrations import run_migrations

    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Path 1 smoke: Full Transcript Knowledge Extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smoke_path1_transcript_extraction(
    tmp_path: Path, knowledge_conn: duckdb.DuckDBPyConnection
) -> None:
    """Smoke: reconstruct_transcript feeds full content to extract_and_store_knowledge.

    Verifies that Path 1 from design.md is live:
    _extract_knowledge_and_findings → reconstruct_transcript → extract_and_store_knowledge
    """
    from agent_fox.knowledge.agent_trace import reconstruct_transcript

    # Create a JSONL trace file with substantial content
    audit_dir = tmp_path / ".agent-fox" / "audit"
    audit_dir.mkdir(parents=True)
    run_id = "smoke-run-1"
    node_id = "05_foo:1"
    events = [
        {
            "event_type": "assistant.message",
            "run_id": run_id,
            "node_id": node_id,
            "content": f"This is assistant message {i} with substantial content: " + "X" * 500,
        }
        for i in range(5)
    ]
    jsonl_path = audit_dir / f"agent_{run_id}.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(e) for e in events))

    # Reconstruct transcript
    transcript = reconstruct_transcript(audit_dir, run_id, node_id)

    # Verify transcript contains all messages
    assert len(transcript) > 2000, (
        f"Reconstructed transcript should be > 2000 chars, got {len(transcript)}"
    )
    for i in range(5):
        assert f"assistant message {i}" in transcript

    # Pass to extract_and_store_knowledge with mocked LLM
    from agent_fox.engine.knowledge_harvest import extract_and_store_knowledge
    from agent_fox.knowledge.db import KnowledgeDB

    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = knowledge_conn

    llm_response = json.dumps(
        [
            {
                "content": "Always use context managers when opening database connections to ensure cleanup.",
                "category": "convention",
                "confidence": "high",
                "keywords": ["database", "context", "manager"],
            }
        ]
    )

    async def fake_extract(t, spec, *a, **kw):
        from agent_fox.knowledge.extraction import _parse_extraction_response
        return _parse_extraction_response(llm_response, spec)

    with patch("agent_fox.engine.knowledge_harvest.extract_facts", side_effect=fake_extract):
        await extract_and_store_knowledge(transcript, "05_foo", node_id, "SIMPLE", db)

    # Verify fact was stored
    row = knowledge_conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()
    assert row[0] >= 1, "At least one fact should be stored from transcript extraction"


# ---------------------------------------------------------------------------
# Path 2 smoke: LLM-Powered Git Commit Extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smoke_path2_git_llm_extraction(
    tmp_path: Path, knowledge_conn: duckdb.DuckDBPyConnection
) -> None:
    """Smoke: ingest_git_commits uses LLM extraction and stores structured facts.

    Verifies that Path 2 from design.md is live:
    ingest_git_commits → _extract_git_facts_llm → store in memory_facts
    """
    from agent_fox.knowledge.ingest import KnowledgeIngestor

    mock_embedder = MagicMock()
    mock_embedder.embedding_dimensions = 384
    mock_embedder.embed_text.return_value = [0.0] * 384

    ingestor = KnowledgeIngestor(knowledge_conn, mock_embedder, tmp_path)

    git_output = (
        "\x1eabc123\x002026-01-01T10:00:00Z\x00feat: implement async retry with exponential backoff"
        "\x1edef456\x002026-01-02T10:00:00Z\x00fix: handle connection timeout in database layer properly"
    )

    llm_response = json.dumps(
        [
            {
                "content": "Use exponential backoff for retry logic to avoid thundering herd in API calls.",
                "category": "pattern",
                "confidence": "high",
                "keywords": ["retry", "backoff", "api"],
            }
        ]
    )

    with (
        patch(
            "subprocess.run",
            return_value=MagicMock(returncode=0, stdout=git_output),
        ),
        patch(
            "agent_fox.core.client.ai_call",
            new=AsyncMock(return_value=(llm_response, MagicMock())),
        ),
    ):
        result = await ingestor.ingest_git_commits()

    assert result.facts_added >= 1, (
        "LLM extraction should produce at least 1 fact from git commits"
    )

    rows = knowledge_conn.execute(
        "SELECT category, confidence FROM memory_facts WHERE category = 'git'"
    ).fetchall()
    assert len(rows) >= 1
    # Confidence should be LLM-derived, not a fixed value
    assert all(c in (0.9, 0.6, 0.3) for _, c in rows), (
        "Git fact confidence should be LLM-derived (high=0.9, medium=0.6, low=0.3)"
    )


# ---------------------------------------------------------------------------
# Path 3 smoke: Entity Signal Activation via Prior Touched Files
# ---------------------------------------------------------------------------


def test_smoke_path3_entity_signal_activation(
    knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    """Smoke: _query_prior_touched_files returns paths that feed entity signal.

    Verifies that Path 3 from design.md is live.
    """
    from agent_fox.core.config import KnowledgeConfig
    from agent_fox.engine.session_lifecycle import NodeSessionRunner
    from agent_fox.knowledge.db import KnowledgeDB

    # Seed prior sessions
    knowledge_conn.execute(
        """
        INSERT INTO session_outcomes (id, spec_name, task_group, node_id, touched_path, status, created_at)
        VALUES
            (?::UUID, '05_foo', '1', '05_foo:1', 'src/main.py,src/utils.py', 'completed', CURRENT_TIMESTAMP),
            (?::UUID, '05_foo', '2', '05_foo:2', 'src/api.py', 'completed', CURRENT_TIMESTAMP)
        """,
        [str(uuid.uuid4()), str(uuid.uuid4())],
    )

    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = knowledge_conn

    runner = NodeSessionRunner.__new__(NodeSessionRunner)
    runner._node_id = "05_foo:3"
    runner._spec_name = "05_foo"
    runner._run_id = "test-run"
    runner._config = KnowledgeConfig()
    runner._knowledge_db = db
    runner._sink_dispatcher = None
    runner._embedder = None
    runner._archetype = "coder"

    paths = runner._query_prior_touched_files("05_foo")

    assert len(paths) > 0, "Should return prior touched files"
    assert "src/main.py" in paths
    assert "src/utils.py" in paths
    assert "src/api.py" in paths
    # No duplicates
    assert len(paths) == len(set(paths))


# ---------------------------------------------------------------------------
# Path 4 smoke: Audit Report Consumption
# ---------------------------------------------------------------------------


def test_smoke_path4_audit_findings_in_db(
    knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    """Smoke: Audit findings persisted to review_findings with category='audit'.

    Verifies that Path 4 from design.md is live:
    persist_auditor_results → insert_findings with category='audit'
    """
    from agent_fox.session.auditor_output import persist_auditor_results
    from agent_fox.session.convergence import AuditEntry, AuditResult

    audit_result = AuditResult(
        entries=[
            AuditEntry(severity="critical", description="Missing error handling in auth module"),
            AuditEntry(severity="major", description="Race condition in session cleanup"),
        ],
        overall_verdict="FAIL",
        summary="2 critical findings",
    )

    spec_dir = tmp_path / "05_foo"
    spec_dir.mkdir()

    persist_auditor_results(
        spec_dir,
        audit_result,
        attempt=1,
        project_root=tmp_path,
        conn=knowledge_conn,
    )

    rows = knowledge_conn.execute(
        "SELECT severity, description, category FROM review_findings WHERE category = 'audit'"
    ).fetchall()

    assert len(rows) == 2, f"Expected 2 audit findings, got {len(rows)}"
    assert all(r[2] == "audit" for r in rows)


# ---------------------------------------------------------------------------
# Path 5 smoke: Cold-Start Detection
# ---------------------------------------------------------------------------


def test_smoke_path5_cold_start_skip(
    knowledge_conn: duckdb.DuckDBPyConnection,
) -> None:
    """Smoke: Empty knowledge store → cold_start=True, no signal queries.

    Verifies that Path 5 from design.md is live.
    """
    from agent_fox.core.config import RetrievalConfig
    from agent_fox.knowledge.retrieval import AdaptiveRetriever

    retriever = AdaptiveRetriever(knowledge_conn, RetrievalConfig(), embedder=None)

    result = retriever.retrieve(
        spec_name="new_spec",
        archetype="coder",
        node_status="fresh",
        touched_files=[],
        task_description="implement feature",
    )

    assert result.cold_start is True
    # No facts were returned (no signals ran)
    assert result.anchor_count == 0


# ---------------------------------------------------------------------------
# Path 6 smoke: Compaction Improvements
# ---------------------------------------------------------------------------


def test_smoke_path6_compaction_with_substring_supersede(
    knowledge_conn: duckdb.DuckDBPyConnection,
) -> None:
    """Smoke: compact() runs _substring_supersede as part of the pipeline.

    Verifies that Path 6 from design.md is live.
    """
    from agent_fox.knowledge.compaction import compact

    conn = knowledge_conn
    # Insert a substring fact pair
    fact_a_id = str(uuid.uuid4())
    fact_b_id = str(uuid.uuid4())

    content_a = "Use retry logic"
    content_b = "Use retry logic with exponential backoff for API calls"
    conn.execute(
        """
        INSERT INTO memory_facts (id, content, category, spec_name, confidence, created_at)
        VALUES
            (?::UUID, ?, 'pattern', 'spec1', 0.8, '2026-01-01 10:00:00'),
            (?::UUID, ?, 'pattern', 'spec1', 0.8, '2026-01-01 11:00:00')
        """,
        [fact_a_id, content_a, fact_b_id, content_b],
    )

    original, surviving = compact(conn)

    assert original == 2
    assert surviving == 1, (
        "Substring compaction should reduce 2 facts to 1 (shorter is superseded by longer)"
    )


# ---------------------------------------------------------------------------
# Path 7 smoke: Retrieval Quality Audit Event
# ---------------------------------------------------------------------------


def test_smoke_path7_retrieval_audit_event(
    knowledge_conn: duckdb.DuckDBPyConnection,
) -> None:
    """Smoke: AdaptiveRetriever.retrieve emits knowledge.retrieval audit event.

    Verifies that Path 7 from design.md is live.
    """
    from agent_fox.core.config import RetrievalConfig
    from agent_fox.knowledge.audit import AuditEventType
    from agent_fox.knowledge.retrieval import AdaptiveRetriever

    conn = knowledge_conn
    fact_content = "A detailed fact with enough content to be retrieved by the retriever"
    # Insert facts so retrieval is non-empty
    for _ in range(3):
        fact_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO memory_facts
                (id, content, category, spec_name, confidence, keywords, created_at)
            VALUES (?::UUID, ?, 'decision', '05_foo', 0.9, ['05_foo', 'test'], CURRENT_TIMESTAMP)
            """,
            [fact_id, fact_content],
        )

    emitted_events: list = []
    mock_sink = MagicMock()
    mock_sink.emit_audit_event.side_effect = emitted_events.append

    retriever = AdaptiveRetriever(conn, RetrievalConfig(), embedder=None)
    retriever._sink_dispatcher = mock_sink
    retriever._node_id = "05_foo:1"

    retriever.retrieve(
        spec_name="05_foo",
        archetype="coder",
        node_status="fresh",
        touched_files=[],
        task_description="implement feature",
        keywords=["05_foo"],
    )

    knowledge_retrieval_events = [
        e for e in emitted_events
        if hasattr(e, "event_type") and e.event_type == AuditEventType.KNOWLEDGE_RETRIEVAL
    ]
    assert len(knowledge_retrieval_events) == 1, (
        f"Expected exactly 1 knowledge.retrieval audit event, got {len(knowledge_retrieval_events)}"
    )

    payload = knowledge_retrieval_events[0].payload
    assert "spec_name" in payload
    assert "facts_returned" in payload
    assert payload["cold_start"] is False
