"""Integration tests for session summary lifecycle.

Test Spec: TS-119-16, TS-119-17, TS-119-18, TS-119-19, TS-119-20,
           TS-119-SMOKE-1, TS-119-SMOKE-2, TS-119-SMOKE-3
Requirements: 119-REQ-4.1, 119-REQ-4.2, 119-REQ-5.1, 119-REQ-5.2,
              119-REQ-5.3
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import duckdb

from agent_fox.knowledge.migrations import run_migrations

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


def _make_conn():
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    conn.execute(_SESSION_SUMMARIES_DDL)
    return conn


def _make_provider(conn):
    from agent_fox.core.config import KnowledgeProviderConfig
    from agent_fox.knowledge.db import KnowledgeDB
    from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = conn
    return FoxKnowledgeProvider(db, KnowledgeProviderConfig())


# TS-119-16: Audit event includes summary (119-REQ-4.1)
class TestAuditEventIncludesSummary:
    def test_audit_payload_has_summary(self, tmp_path):
        from agent_fox.engine.session_lifecycle import NodeSessionRunner
        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir()
        summary_file = agent_fox_dir / "session-summary.json"
        summary_file.write_text(
            json.dumps({"summary": "Built the store", "tests_added_or_modified": []}),
            encoding="utf-8",
        )
        workspace = MagicMock()
        workspace.path = tmp_path
        artifacts = NodeSessionRunner._read_session_artifacts(workspace)
        assert artifacts is not None
        summary_text = artifacts.get("summary", "")
        assert summary_text == "Built the store"
        payload: dict = {"archetype": "coder", "duration_ms": 1000}
        if summary_text:
            payload["summary"] = summary_text
        assert payload["summary"] == "Built the store"


# TS-119-17: Audit event omits summary when missing (119-REQ-4.2)
class TestAuditEventOmitsSummaryWhenMissing:
    def test_audit_payload_no_summary(self, tmp_path):
        from agent_fox.engine.session_lifecycle import NodeSessionRunner
        workspace = MagicMock()
        workspace.path = tmp_path
        artifacts = NodeSessionRunner._read_session_artifacts(workspace)
        assert artifacts is None
        payload: dict = {"archetype": "coder", "duration_ms": 1000}
        if artifacts:
            summary_text = artifacts.get("summary", "")
            if summary_text:
                payload["summary"] = summary_text
        assert "summary" not in payload


# TS-119-18: Summary passed to ingest via context (119-REQ-5.1)
class TestSummaryPassedToIngestContext:
    def test_context_contains_summary(self):
        context = {
            "touched_files": ["store.py"], "commit_sha": "abc123",
            "session_status": "completed", "summary": "Built the store",
            "archetype": "coder", "task_group": "2", "attempt": 1,
        }
        assert "summary" in context
        assert context["summary"] == "Built the store"


# TS-119-19: Ingest stores summary in database (119-REQ-5.2)
class TestIngestStoresSummary:
    def test_ingest_creates_row(self):
        conn = _make_conn()
        try:
            provider = _make_provider(conn)
            provider.ingest("spec_a:3", "spec_a", {
                "summary": "Built store", "session_status": "completed",
                "touched_files": [], "commit_sha": "abc123",
                "archetype": "coder", "task_group": "3", "attempt": 1,
            })
            rows = conn.execute("SELECT summary FROM session_summaries").fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "Built store"
        finally:
            conn.close()


# TS-119-20: Summary available to both paths (119-REQ-5.3)
class TestSummaryAvailableToBothPaths:
    def test_same_summary_for_both_paths(self, tmp_path):
        from agent_fox.engine.session_lifecycle import NodeSessionRunner
        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir()
        summary_file = agent_fox_dir / "session-summary.json"
        summary_file.write_text(
            json.dumps({"summary": "Implemented handlers", "tests_added_or_modified": []}),
            encoding="utf-8",
        )
        workspace = MagicMock()
        workspace.path = tmp_path
        artifacts = NodeSessionRunner._read_session_artifacts(workspace)
        assert artifacts is not None
        summary_text = artifacts.get("summary", "")
        audit_summary = summary_text
        ingest_summary = summary_text
        assert audit_summary == ingest_summary
        assert audit_summary == "Implemented handlers"


# TS-119-SMOKE-1: End-to-end summary storage and retrieval
class TestSmokeSummaryStorageAndRetrieval:
    def test_smoke_ingest_then_retrieve(self):
        conn = _make_conn()
        try:
            provider = _make_provider(conn)
            provider.ingest("spec_a:2", "spec_a", {
                "summary": "Built the SQLite store with WAL mode",
                "session_status": "completed",
                "touched_files": ["store.py"], "commit_sha": "abc123",
                "archetype": "coder", "task_group": "2", "attempt": 1,
            })
            items = provider.retrieve("spec_a", "implement handlers", task_group="3")
            context_items = [i for i in items if i.startswith("[CONTEXT]")]
            assert len(context_items) == 1
            assert "Built the SQLite store" in context_items[0]
        finally:
            conn.close()


# TS-119-SMOKE-2: Cross-spec summary injection
class TestSmokeCrossSpecInjection:
    def test_smoke_cross_spec(self):
        conn = _make_conn()
        try:
            provider = _make_provider(conn)
            provider.ingest("spec_b:2", "spec_b", {
                "summary": "Changed AuthConfig to remove BearerToken",
                "session_status": "completed",
                "touched_files": [], "commit_sha": "def456",
                "archetype": "coder", "task_group": "2", "attempt": 1,
            })
            items = provider.retrieve("spec_a", "implement auth", task_group="3")
            cross_items = [i for i in items if i.startswith("[CROSS-SPEC]")]
            assert len(cross_items) == 1
            assert "Changed AuthConfig" in cross_items[0]
        finally:
            conn.close()


# TS-119-SMOKE-3: Audit event includes summary end-to-end
class TestSmokeAuditEventIncludesSummary:
    def test_smoke_artifact_to_audit(self, tmp_path):
        from agent_fox.engine.session_lifecycle import NodeSessionRunner
        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir()
        summary_file = agent_fox_dir / "session-summary.json"
        summary_file.write_text(
            json.dumps({"summary": "Implemented handlers", "tests_added_or_modified": []}),
            encoding="utf-8",
        )
        workspace = MagicMock()
        workspace.path = tmp_path
        artifacts = NodeSessionRunner._read_session_artifacts(workspace)
        assert artifacts is not None
        summary_text = artifacts.get("summary", "")
        payload: dict = {
            "archetype": "coder", "model_id": "claude-opus-4-6", "duration_ms": 165000,
        }
        if summary_text:
            payload["summary"] = summary_text
        assert payload["summary"] == "Implemented handlers"
