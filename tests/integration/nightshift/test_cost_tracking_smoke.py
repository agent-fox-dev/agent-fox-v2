"""Integration smoke tests for nightshift cost tracking.

Test Spec: TS-91-SMOKE-1, TS-91-SMOKE-2, TS-91-SMOKE-3
Execution Paths: 1, 2, 3 from design.md
Requirements: 91-REQ-6.1, 91-REQ-6.2, 91-REQ-6.3

These tests use a real in-memory DuckDB with the audit schema, real
SinkDispatcher and DuckDBSink. They do NOT mock emit_audit_event or
DuckDBSink — they verify the entire write path.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest

from agent_fox.knowledge.duckdb_sink import DuckDBSink
from agent_fox.knowledge.sink import SinkDispatcher

# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_AUDIT_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id          VARCHAR PRIMARY KEY,
    timestamp   TIMESTAMP NOT NULL,
    run_id      VARCHAR NOT NULL,
    event_type  VARCHAR NOT NULL,
    node_id     VARCHAR,
    session_id  VARCHAR,
    archetype   VARCHAR,
    severity    VARCHAR NOT NULL,
    payload     JSON NOT NULL
)
"""


def _create_audit_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Initialize the audit_events table in an in-memory DuckDB."""
    conn.execute(_AUDIT_EVENTS_DDL)


def _make_in_memory_sink() -> tuple[duckdb.DuckDBPyConnection, SinkDispatcher]:
    """Create a real in-memory DuckDB connection with audit schema and a SinkDispatcher."""
    conn = duckdb.connect(":memory:")
    _create_audit_schema(conn)
    db_sink = DuckDBSink(conn)
    dispatcher = SinkDispatcher([db_sink])
    return conn, dispatcher


# ---------------------------------------------------------------------------
# Config / issue helpers
# ---------------------------------------------------------------------------


def _make_config() -> MagicMock:
    config = MagicMock()
    config.platform.type = "github"
    config.orchestrator.max_cost = None
    config.orchestrator.max_sessions = None
    config.orchestrator.retries_before_escalation = 1
    config.orchestrator.max_retries = 3
    config.archetypes = None
    config.pricing = MagicMock()
    config.pricing.models = {}
    config.theme = None
    return config


def _make_issue(number: int = 42):  # type: ignore[no-untyped-def]
    from agent_fox.platform.github import IssueResult

    return IssueResult(
        number=number,
        title=f"Fix issue #{number}",
        html_url=f"https://github.com/test/repo/issues/{number}",
    )


def _make_session_outcome(
    input_tokens: int = 1200,
    output_tokens: int = 300,
    duration_ms: int = 10_000,
    status: str = "completed",
    response: str = "",
) -> MagicMock:
    outcome = MagicMock()
    outcome.input_tokens = input_tokens
    outcome.output_tokens = output_tokens
    outcome.cache_read_input_tokens = 0
    outcome.cache_creation_input_tokens = 0
    outcome.duration_ms = duration_ms
    outcome.status = status
    outcome.response = response
    outcome.error_message = None
    return outcome


def _make_workspace():  # type: ignore[no-untyped-def]
    from agent_fox.workspace import WorkspaceInfo

    return WorkspaceInfo(
        path=Path("/tmp/mock-worktree"),
        branch="fix/test-branch",
        spec_name="fix-issue-42",
        task_group=0,
    )


# ---------------------------------------------------------------------------
# TS-91-SMOKE-1: Fix session costs appear in status report
# Execution Path: 1 from design.md
# Requirements: 91-REQ-6.1, 91-REQ-6.2, 91-REQ-6.3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smoke_fix_session_costs_in_status_report() -> None:
    """Fix pipeline emits session.complete events visible in build_status_report_from_audit.

    Uses real DuckDB + real DuckDBSink + real SinkDispatcher. Does NOT mock
    emit_audit_event or DuckDBSink.
    """
    from agent_fox.nightshift.fix_pipeline import FixPipeline
    from agent_fox.reporting.status import build_status_report_from_audit

    conn, sink = _make_in_memory_sink()

    config = _make_config()
    mock_platform = AsyncMock()

    # FAILS at construction until FixPipeline accepts sink_dispatcher
    pipeline = FixPipeline(config, mock_platform, sink_dispatcher=sink)

    mock_outcome = _make_session_outcome(input_tokens=1500, output_tokens=400)

    with (
        patch.object(pipeline, "_setup_workspace", AsyncMock(return_value=_make_workspace())),
        patch.object(pipeline, "_cleanup_workspace", AsyncMock()),
        # Mock _run_session to return a known SessionOutcome without running Claude
        patch.object(pipeline, "_run_session", AsyncMock(return_value=mock_outcome)),
        # Mock the coder-reviewer loop since we're only testing triage cost emission
        patch.object(pipeline, "_coder_review_loop", AsyncMock(return_value=False)),
    ):
        await pipeline.process_issue(_make_issue(42), issue_body="Fix the critical bug")

    # Verify audit_events were written to DuckDB
    rows = conn.execute("SELECT event_type, payload FROM audit_events WHERE event_type = 'session.complete'").fetchall()

    # FAILS until FixPipeline emits session.complete events
    assert len(rows) >= 1, "process_issue must emit at least one session.complete event to DuckDB"

    # Verify the status report aggregates those costs
    report = build_status_report_from_audit(conn)
    assert report is not None, "build_status_report_from_audit must return a report"

    # FAILS until total_cost is populated from the emitted events
    assert report.total_cost > 0, f"StatusReport.total_cost must be > 0 after fix session, got {report.total_cost}"

    # FAILS until cost_by_archetype includes fix session archetypes
    night_shift_archetypes = {"triage", "fix_coder", "fix_reviewer"}
    matched = night_shift_archetypes & set(report.cost_by_archetype.keys())
    assert matched, (
        f"cost_by_archetype must include at least one of {night_shift_archetypes}, "
        f"got: {set(report.cost_by_archetype.keys())}"
    )


# ---------------------------------------------------------------------------
# TS-91-SMOKE-2: Auxiliary costs appear in status report
# Execution Path: 2 from design.md
# Requirement: 91-REQ-6.3
# ---------------------------------------------------------------------------


def test_smoke_auxiliary_costs_in_status_report() -> None:
    """emit_auxiliary_cost writes to DuckDB and appears in the status report.

    Uses real DuckDB + real DuckDBSink + real SinkDispatcher. Does NOT mock
    emit_audit_event or DuckDBSink.
    """
    # FAILS with ModuleNotFoundError until cost_helpers.py is created
    from agent_fox.nightshift.cost_helpers import emit_auxiliary_cost  # type: ignore[import]

    from agent_fox.reporting.status import build_status_report_from_audit

    conn, sink = _make_in_memory_sink()

    # Mock API response with known token counts
    mock_response = MagicMock()
    mock_response.usage.input_tokens = 800
    mock_response.usage.output_tokens = 150
    mock_response.usage.cache_read_input_tokens = 0
    mock_response.usage.cache_creation_input_tokens = 0

    mock_pricing = MagicMock()
    mock_pricing.models = {}

    # Emit directly (simulating a critic call)
    emit_auxiliary_cost(
        sink,
        "smoke-run-1",
        "hunt_critic",
        mock_response,
        "claude-opus-4-5",
        mock_pricing,
    )

    # Verify the event is in DuckDB
    rows = conn.execute("SELECT payload FROM audit_events WHERE event_type = 'session.complete'").fetchall()
    assert len(rows) >= 1, "emit_auxiliary_cost must write a session.complete row to DuckDB"

    # Parse payload of first row to verify archetype
    payload = json.loads(rows[0][0]) if isinstance(rows[0][0], str) else rows[0][0]
    assert payload.get("archetype") == "hunt_critic", (
        f"Expected archetype='hunt_critic' in payload, got: {payload.get('archetype')}"
    )

    # Verify status report aggregates it
    report = build_status_report_from_audit(conn)
    assert report is not None
    assert report.total_cost > 0, (
        f"StatusReport.total_cost must be > 0 after auxiliary cost emission, got {report.total_cost}"
    )
    assert "hunt_critic" in report.cost_by_archetype, (
        f"cost_by_archetype must include 'hunt_critic', got: {set(report.cost_by_archetype.keys())}"
    )


# ---------------------------------------------------------------------------
# TS-91-SMOKE-3: No JSONL audit files written
# Execution Path: 3 from design.md
# Requirements: 91-REQ-5.1 (Property 6 from design.md)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smoke_no_jsonl_audit_files_written(tmp_path: Path) -> None:
    """After migration, night-shift operational events go to DuckDB, not JSONL.

    Uses real DuckDB + real DuckDBSink + real SinkDispatcher. Does NOT mock
    emit_audit_event.
    """
    import os

    from agent_fox.nightshift.engine import NightShiftEngine

    conn, sink = _make_in_memory_sink()
    config = _make_config()
    mock_platform = AsyncMock()

    # Change to tmp_path so any accidental JSONL writes would go to tmp_path/.agent-fox/audit/
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # FAILS at construction until NightShiftEngine accepts sink_dispatcher
        engine = NightShiftEngine(
            config=config,
            platform=mock_platform,
            sink_dispatcher=sink,
        )

        issue = _make_issue(1)

        # Mock the fix pipeline so we exercise the engine without running Claude
        with patch(
            "agent_fox.nightshift.engine.FixPipeline",
            autospec=True,
        ) as mock_pipeline_cls:
            mock_pipeline = MagicMock()
            mock_pipeline.process_issue = AsyncMock(
                return_value=MagicMock(sessions_run=1, input_tokens=100, output_tokens=50)
            )
            mock_pipeline_cls.return_value = mock_pipeline

            await engine._process_fix(issue, issue_body="Fix the bug")

    finally:
        os.chdir(original_cwd)

    # FAILS until JSONL-based audit.py is removed
    audit_dir = tmp_path / ".agent-fox" / "audit"
    assert not audit_dir.exists(), (
        f"JSONL audit directory {audit_dir} must NOT be created — all audit events must go to DuckDB"
    )

    # Verify operational events ARE in DuckDB
    rows = conn.execute("SELECT event_type FROM audit_events WHERE event_type LIKE 'night_shift%'").fetchall()
    # FAILS until engine uses standard emit_audit_event with the shared sink
    assert len(rows) >= 1, "NightShiftEngine operational events (night_shift.*) must appear in DuckDB audit_events"
