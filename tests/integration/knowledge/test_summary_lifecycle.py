"""Integration tests for session summary lifecycle.

Test Spec: TS-119-16, TS-119-17, TS-119-18, TS-119-19, TS-119-20,
           TS-119-SMOKE-1, TS-119-SMOKE-2, TS-119-SMOKE-3
Requirements: 119-REQ-4.1, 119-REQ-4.2, 119-REQ-5.1, 119-REQ-5.2,
              119-REQ-5.3
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest

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


def _make_provider(conn, run_id=None):
    from agent_fox.core.config import KnowledgeProviderConfig
    from agent_fox.knowledge.db import KnowledgeDB
    from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = conn
    provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())
    if run_id is not None:
        provider._run_id = run_id
    return provider


# ---------------------------------------------------------------------------
# Helpers for audit event capture in _run_and_harvest tests
# ---------------------------------------------------------------------------


def _make_runner(
    node_id="spec_a:2",
    archetype="coder",
    sink=None,
    knowledge_provider=None,
    run_id="run-1",
):
    """Create a NodeSessionRunner with mocked dependencies."""
    from agent_fox.core.config import AgentFoxConfig
    from agent_fox.engine.session_lifecycle import NodeSessionRunner
    from agent_fox.knowledge.db import KnowledgeDB

    mock_kb = MagicMock(spec=KnowledgeDB)
    config = AgentFoxConfig()
    return NodeSessionRunner(
        node_id,
        config,
        archetype=archetype,
        knowledge_db=mock_kb,
        sink_dispatcher=sink,
        knowledge_provider=knowledge_provider,
        run_id=run_id,
    )


def _fake_outcome(status="completed"):
    """Create a fake SessionOutcome for testing."""
    from agent_fox.knowledge.sink import SessionOutcome

    return SessionOutcome(
        spec_name="spec_a",
        task_group="2",
        node_id="spec_a:2",
        status=status,
        input_tokens=100,
        output_tokens=200,
        duration_ms=5000,
    )


# TS-119-16: Audit event includes summary (119-REQ-4.1)
class TestAuditEventIncludesSummary:
    def test_audit_payload_has_summary_via_ingest(self, tmp_path):
        """Verify that when a summary artifact exists, the system stores it.

        Tests the DB storage path (ingest) to confirm the artifact
        flows through to the knowledge provider.
        """
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir()
        (agent_fox_dir / "session-summary.json").write_text(
            json.dumps({"summary": "Built the store", "tests_added_or_modified": []}),
            encoding="utf-8",
        )
        workspace = MagicMock()
        workspace.path = tmp_path

        artifacts = NodeSessionRunner._read_session_artifacts(workspace)
        assert artifacts is not None
        summary_text = artifacts.get("summary", "")

        conn = _make_conn()
        try:
            provider = _make_provider(conn, run_id="run-1")
            provider.ingest("spec_a:2", "spec_a", {
                "summary": summary_text,
                "session_status": "completed",
                "touched_files": [], "commit_sha": "abc123",
                "archetype": "coder", "task_group": "2", "attempt": 1,
            })

            rows = conn.execute(
                "SELECT summary FROM session_summaries"
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "Built the store"
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_audit_event_payload_contains_summary(self, tmp_path):
        """Verify session.complete audit event payload contains summary.

        Exercises _run_and_harvest path: artifact reading, audit event
        emission with summary in payload.

        Requirements: 119-REQ-4.1
        """
        from agent_fox.knowledge.audit import AuditEventType

        workspace = MagicMock()
        workspace.path = tmp_path

        audit_calls = []

        def capture_emit(sink_arg, run_id, event_type, **kwargs):
            audit_calls.append({
                "event_type": event_type,
                "payload": kwargs.get("payload", {}),
            })

        runner = _make_runner(sink=MagicMock())

        with (
            patch.object(
                runner, "_execute_session",
                new_callable=AsyncMock,
                return_value=_fake_outcome(),
            ),
            patch.object(
                runner, "_harvest_and_integrate",
                new_callable=AsyncMock,
                return_value=("completed", None, ["store.py"], False),
            ),
            patch(
                "agent_fox.engine.session_lifecycle._capture_develop_head",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "agent_fox.engine.session_lifecycle.emit_audit_event",
                side_effect=capture_emit,
            ),
            patch.object(
                runner, "_extract_knowledge_and_findings",
                new_callable=AsyncMock,
            ),
            patch.object(
                runner, "_read_session_artifacts",
                return_value={"summary": "Built the store"},
            ),
        ):
            record = await runner._run_and_harvest(
                "spec_a:2", 1, workspace, "sys", "task", Path("/tmp"),
            )

        assert record.status == "completed"
        complete_events = [
            c for c in audit_calls
            if c["event_type"] == AuditEventType.SESSION_COMPLETE
        ]
        assert len(complete_events) == 1
        payload = complete_events[0]["payload"]
        assert "summary" in payload
        assert payload["summary"] == "Built the store"


# TS-119-17: Audit event omits summary when missing (119-REQ-4.2)
class TestAuditEventOmitsSummaryWhenMissing:
    def test_audit_payload_no_summary_via_ingest(self, tmp_path):
        """Verify that when no summary artifact exists, no summary is stored."""
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        workspace = MagicMock()
        workspace.path = tmp_path
        artifacts = NodeSessionRunner._read_session_artifacts(workspace)
        assert artifacts is None

        conn = _make_conn()
        try:
            provider = _make_provider(conn, run_id="run-1")

            # Precondition: a completed session WITH a summary stores a row.
            provider.ingest("spec_a:1", "spec_a", {
                "summary": "Precondition text",
                "session_status": "completed",
                "touched_files": [], "commit_sha": "abc",
                "archetype": "coder", "task_group": "1", "attempt": 1,
            })
            precondition = conn.execute(
                "SELECT COUNT(*) FROM session_summaries"
            ).fetchone()
            assert precondition[0] == 1

            # When no summary is present, no row is added
            provider.ingest("spec_a:2", "spec_a", {
                "session_status": "completed",
                "touched_files": [], "commit_sha": "abc",
                "archetype": "coder", "task_group": "2", "attempt": 1,
            })
            total = conn.execute(
                "SELECT COUNT(*) FROM session_summaries"
            ).fetchone()
            assert total[0] == 1  # Still 1
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_audit_event_payload_omits_summary_when_missing(self, tmp_path):
        """Verify session.complete audit event payload does NOT contain
        'summary' key when no summary artifact is present.

        Requirements: 119-REQ-4.2
        """
        from agent_fox.knowledge.audit import AuditEventType

        workspace = MagicMock()
        workspace.path = tmp_path

        audit_calls = []

        def capture_emit(sink_arg, run_id, event_type, **kwargs):
            audit_calls.append({
                "event_type": event_type,
                "payload": kwargs.get("payload", {}),
            })

        runner = _make_runner(sink=MagicMock())

        with (
            patch.object(
                runner, "_execute_session",
                new_callable=AsyncMock,
                return_value=_fake_outcome(),
            ),
            patch.object(
                runner, "_harvest_and_integrate",
                new_callable=AsyncMock,
                return_value=("completed", None, [], False),
            ),
            patch(
                "agent_fox.engine.session_lifecycle._capture_develop_head",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "agent_fox.engine.session_lifecycle.emit_audit_event",
                side_effect=capture_emit,
            ),
            patch.object(
                runner, "_extract_knowledge_and_findings",
                new_callable=AsyncMock,
            ),
            patch.object(
                runner, "_read_session_artifacts",
                return_value=None,
            ),
        ):
            record = await runner._run_and_harvest(
                "spec_a:2", 1, workspace, "sys", "task", Path("/tmp"),
            )

        assert record.status == "completed"
        complete_events = [
            c for c in audit_calls
            if c["event_type"] == AuditEventType.SESSION_COMPLETE
        ]
        assert len(complete_events) == 1
        payload = complete_events[0]["payload"]
        assert "summary" not in payload


# TS-119-18: Summary passed to ingest via context (119-REQ-5.1)
class TestSummaryPassedToIngestContext:
    def test_context_contains_summary(self):
        """Verify that ingest receives the summary from context and stores it."""
        conn = _make_conn()
        try:
            provider = _make_provider(conn, run_id="run-1")
            provider.ingest("spec_a:2", "spec_a", {
                "summary": "Built the store",
                "session_status": "completed",
                "touched_files": ["store.py"], "commit_sha": "abc123",
                "archetype": "coder", "task_group": "2", "attempt": 1,
            })
            rows = conn.execute(
                "SELECT summary FROM session_summaries"
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "Built the store"
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_ingest_knowledge_passes_summary_in_context(self, tmp_path):
        """Verify _ingest_knowledge() includes the summary string in the
        context dict passed to the knowledge provider's ingest().

        Requirements: 119-REQ-5.1
        """
        mock_provider = MagicMock()
        runner = _make_runner(knowledge_provider=mock_provider)

        runner._ingest_knowledge(
            "spec_a:2",
            ["store.py"],
            "abc123",
            "completed",
            repo_root=Path("/tmp"),
            summary="Built the store",
            archetype="coder",
            task_group="2",
            attempt=1,
        )

        mock_provider.ingest.assert_called_once()
        call_args = mock_provider.ingest.call_args
        context = call_args[0][2]
        assert context["summary"] == "Built the store"
        assert context["archetype"] == "coder"
        assert context["task_group"] == "2"
        assert context["attempt"] == 1


# TS-119-19: Ingest stores summary in database (119-REQ-5.2)
class TestIngestStoresSummary:
    def test_ingest_creates_row(self):
        """Verify that ingest() inserts a summary row with correct fields."""
        conn = _make_conn()
        try:
            provider = _make_provider(conn, run_id="run-1")
            provider.ingest("spec_a:3", "spec_a", {
                "summary": "Built store", "session_status": "completed",
                "touched_files": [], "commit_sha": "abc123",
                "archetype": "coder", "task_group": "3", "attempt": 1,
            })
            rows = conn.execute(
                "SELECT summary, spec_name, task_group, archetype, attempt "
                "FROM session_summaries"
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "Built store"
            assert rows[0][1] == "spec_a"
            assert rows[0][2] == "3"
            assert rows[0][3] == "coder"
            assert rows[0][4] == 1
        finally:
            conn.close()


# TS-119-20: Summary available to both paths (119-REQ-5.3)
class TestSummaryAvailableToBothPaths:
    def test_same_summary_for_both_paths(self, tmp_path):
        """Verify the same summary text from a single artifact read is
        stored by ingest and can be retrieved."""
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir()
        (agent_fox_dir / "session-summary.json").write_text(
            json.dumps({
                "summary": "Implemented handlers",
                "tests_added_or_modified": [],
            }),
            encoding="utf-8",
        )
        workspace = MagicMock()
        workspace.path = tmp_path

        artifacts = NodeSessionRunner._read_session_artifacts(workspace)
        assert artifacts is not None
        summary_text = artifacts.get("summary", "")

        conn = _make_conn()
        try:
            provider = _make_provider(conn, run_id="run-1")
            provider.ingest("spec_a:2", "spec_a", {
                "summary": summary_text,
                "session_status": "completed",
                "touched_files": [], "commit_sha": "abc",
                "archetype": "coder", "task_group": "2", "attempt": 1,
            })

            rows = conn.execute(
                "SELECT summary FROM session_summaries"
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == summary_text
            assert rows[0][0] == "Implemented handlers"

            items = provider.retrieve(
                "spec_a", "implement auth", task_group="3",
            )
            context_items = [i for i in items if i.startswith("[CONTEXT]")]
            assert len(context_items) == 1
            assert "Implemented handlers" in context_items[0]
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_audit_and_ingest_receive_same_summary(self, tmp_path):
        """Verify both audit event payload AND ingest context receive
        the same summary text from a single artifact read.

        Requirements: 119-REQ-5.3
        """
        from agent_fox.knowledge.audit import AuditEventType

        workspace = MagicMock()
        workspace.path = tmp_path

        audit_calls = []
        ingest_contexts = []

        def capture_emit(sink_arg, run_id, event_type, **kwargs):
            audit_calls.append({
                "event_type": event_type,
                "payload": kwargs.get("payload", {}),
            })

        mock_provider = MagicMock()

        def capture_ingest(session_id, spec_name, context):
            ingest_contexts.append(dict(context))

        mock_provider.ingest.side_effect = capture_ingest

        runner = _make_runner(
            sink=MagicMock(), knowledge_provider=mock_provider,
        )

        with (
            patch.object(
                runner, "_execute_session",
                new_callable=AsyncMock,
                return_value=_fake_outcome(),
            ),
            patch.object(
                runner, "_harvest_and_integrate",
                new_callable=AsyncMock,
                return_value=("completed", None, ["handler.py"], False),
            ),
            patch(
                "agent_fox.engine.session_lifecycle._capture_develop_head",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "agent_fox.engine.session_lifecycle.emit_audit_event",
                side_effect=capture_emit,
            ),
            patch.object(
                runner, "_extract_knowledge_and_findings",
                new_callable=AsyncMock,
            ),
            patch.object(
                runner, "_read_session_artifacts",
                return_value={"summary": "Implemented handlers"},
            ),
        ):
            record = await runner._run_and_harvest(
                "spec_a:2", 1, workspace, "sys", "task", Path("/tmp"),
            )

        assert record.status == "completed"

        # Audit event path
        complete_events = [
            c for c in audit_calls
            if c["event_type"] == AuditEventType.SESSION_COMPLETE
        ]
        assert len(complete_events) == 1
        audit_summary = complete_events[0]["payload"].get("summary")

        # Ingest path
        assert len(ingest_contexts) == 1
        ingest_summary = ingest_contexts[0].get("summary")

        # Both paths receive the same summary
        assert audit_summary is not None
        assert ingest_summary is not None
        assert audit_summary == ingest_summary
        assert audit_summary == "Implemented handlers"


# TS-119-SMOKE-1: End-to-end summary storage and retrieval
class TestSmokeSummaryStorageAndRetrieval:
    def test_smoke_ingest_then_retrieve(self):
        """End-to-end: ingest a summary for group 2, retrieve for group 3."""
        conn = _make_conn()
        try:
            provider = _make_provider(conn, run_id="run-1")
            provider.ingest("spec_a:2", "spec_a", {
                "summary": "Built the SQLite store with WAL mode",
                "session_status": "completed",
                "touched_files": ["store.py"], "commit_sha": "abc123",
                "archetype": "coder", "task_group": "2", "attempt": 1,
            })
            items = provider.retrieve(
                "spec_a", "implement handlers", task_group="3",
            )
            context_items = [i for i in items if i.startswith("[CONTEXT]")]
            assert len(context_items) == 1
            assert "Built the SQLite store" in context_items[0]
        finally:
            conn.close()


# TS-119-SMOKE-2: Cross-spec summary injection
class TestSmokeCrossSpecInjection:
    def test_smoke_cross_spec(self):
        """End-to-end: ingest for spec_b, retrieve cross-spec for spec_a."""
        conn = _make_conn()
        try:
            provider = _make_provider(conn, run_id="run-1")
            provider.ingest("spec_b:2", "spec_b", {
                "summary": "Changed AuthConfig to remove BearerToken",
                "session_status": "completed",
                "touched_files": [], "commit_sha": "def456",
                "archetype": "coder", "task_group": "2", "attempt": 1,
            })
            items = provider.retrieve(
                "spec_a", "implement auth", task_group="3",
            )
            cross_items = [i for i in items if i.startswith("[CROSS-SPEC]")]
            assert len(cross_items) == 1
            assert "Changed AuthConfig" in cross_items[0]
        finally:
            conn.close()


# TS-119-SMOKE-3: Audit event includes summary end-to-end
class TestSmokeAuditEventIncludesSummary:
    def test_smoke_artifact_to_db(self, tmp_path):
        """End-to-end: read artifact, ingest, verify storage."""
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir()
        (agent_fox_dir / "session-summary.json").write_text(
            json.dumps({
                "summary": "Implemented handlers",
                "tests_added_or_modified": [],
            }),
            encoding="utf-8",
        )
        workspace = MagicMock()
        workspace.path = tmp_path

        artifacts = NodeSessionRunner._read_session_artifacts(workspace)
        assert artifacts is not None
        summary_text = artifacts["summary"]

        conn = _make_conn()
        try:
            provider = _make_provider(conn, run_id="run-1")
            provider.ingest("spec_a:3", "spec_a", {
                "summary": summary_text,
                "session_status": "completed",
                "touched_files": [], "commit_sha": "abc",
                "archetype": "coder", "task_group": "3", "attempt": 1,
            })

            rows = conn.execute(
                "SELECT summary FROM session_summaries"
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "Implemented handlers"
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_smoke_artifact_to_audit_event(self, tmp_path):
        """End-to-end: read real artifact file, verify audit event emission
        includes the summary in the SESSION_COMPLETE payload.

        NOT mocking _read_session_artifacts to verify full path from
        file -> _run_and_harvest -> emit.

        Requirements: 119-REQ-4.1, 119-REQ-5.3
        """
        from agent_fox.knowledge.audit import AuditEventType

        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir()
        (agent_fox_dir / "session-summary.json").write_text(
            json.dumps({
                "summary": "Implemented handlers",
                "tests_added_or_modified": [],
            }),
            encoding="utf-8",
        )
        workspace = MagicMock()
        workspace.path = tmp_path

        audit_calls = []

        def capture_emit(sink_arg, run_id, event_type, **kwargs):
            audit_calls.append({
                "event_type": event_type,
                "payload": kwargs.get("payload", {}),
            })

        runner = _make_runner(sink=MagicMock())

        with (
            patch.object(
                runner, "_execute_session",
                new_callable=AsyncMock,
                return_value=_fake_outcome(),
            ),
            patch.object(
                runner, "_harvest_and_integrate",
                new_callable=AsyncMock,
                return_value=("completed", None, ["handler.py"], False),
            ),
            patch(
                "agent_fox.engine.session_lifecycle._capture_develop_head",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "agent_fox.engine.session_lifecycle.emit_audit_event",
                side_effect=capture_emit,
            ),
            patch.object(
                runner, "_extract_knowledge_and_findings",
                new_callable=AsyncMock,
            ),
            # NOT mocking _read_session_artifacts to verify full path.
        ):
            record = await runner._run_and_harvest(
                "spec_a:2", 1, workspace, "sys", "task", Path("/tmp"),
            )

        assert record.status == "completed"
        complete_events = [
            c for c in audit_calls
            if c["event_type"] == AuditEventType.SESSION_COMPLETE
        ]
        assert len(complete_events) == 1
        payload = complete_events[0]["payload"]
        assert payload["summary"] == "Implemented handlers"
