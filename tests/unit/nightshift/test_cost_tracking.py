"""Unit tests for nightshift cost tracking.

Test Spec: TS-91-1 through TS-91-13, TS-91-E1, TS-91-E2, TS-91-E3
Requirements: 91-REQ-1.1, 91-REQ-1.2, 91-REQ-1.3, 91-REQ-1.E1,
              91-REQ-2.1, 91-REQ-2.2, 91-REQ-2.E1,
              91-REQ-3.1, 91-REQ-3.2, 91-REQ-3.3, 91-REQ-3.E1,
              91-REQ-4.1, 91-REQ-4.E1,
              91-REQ-5.1, 91-REQ-5.2, 91-REQ-5.3, 91-REQ-5.E1
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.knowledge.sink import SinkDispatcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> MagicMock:
    """Build a mock AgentFoxConfig with minimum required attributes."""
    config = MagicMock()
    config.platform.type = "github"
    config.orchestrator.max_cost = None
    config.orchestrator.max_sessions = None
    config.orchestrator.retries_before_escalation = 1
    config.orchestrator.max_retries = 3
    config.orchestrator.max_budget_usd = 0.0
    # Use empty dicts so resolve_model_tier and other sdk_params resolvers
    # fall back to archetype registry defaults cleanly
    config.archetypes = MagicMock()
    config.archetypes.overrides = {}
    config.archetypes.models = {}
    config.archetypes.max_turns = {}
    config.archetypes.thinking = {}
    config.archetypes.allowlists = {}
    config.models = MagicMock()
    config.models.fallback_model = ""
    config.pricing = MagicMock()
    config.pricing.models = {}
    config.theme = None
    return config


def _make_config_for_cli() -> MagicMock:
    """Build a mock config suitable for CLI invocation."""
    config = MagicMock()
    config.platform.type = "github"
    ns = MagicMock()
    config.night_shift = ns
    config.orchestrator.max_cost = 10.0
    config.theme = None
    config.pricing = MagicMock()
    config.pricing.models = {}
    return config


def _mock_workspace():
    """Return a WorkspaceInfo-like mock."""
    from agent_fox.workspace import WorkspaceInfo

    return WorkspaceInfo(
        path=Path("/tmp/mock-worktree"),
        branch="fix/test-branch",
        spec_name="fix-issue-42",
        task_group=0,
    )


def _mock_spec():
    """Return an InMemorySpec-like mock."""
    from agent_fox.nightshift.spec_builder import InMemorySpec

    spec = MagicMock(spec=InMemorySpec)
    spec.system_context = "test context"
    spec.task_prompt = "fix the bug"
    spec.issue_number = 42
    spec.branch_name = "fix/issue-42"
    return spec


def _mock_session_outcome(
    input_tokens: int = 1000,
    output_tokens: int = 200,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    duration_ms: int = 5000,
    status: str = "completed",
    response: str = "",
    error_message: str | None = None,
) -> MagicMock:
    """Return a mock SessionOutcome with known token counts."""
    outcome = MagicMock()
    outcome.input_tokens = input_tokens
    outcome.output_tokens = output_tokens
    outcome.cache_read_input_tokens = cache_read_input_tokens
    outcome.cache_creation_input_tokens = cache_creation_input_tokens
    outcome.duration_ms = duration_ms
    outcome.status = status
    outcome.response = response
    outcome.error_message = error_message
    return outcome


# ---------------------------------------------------------------------------
# TS-91-1: NightShiftEngine accepts SinkDispatcher
# Requirement: 91-REQ-1.1
# ---------------------------------------------------------------------------


class TestEngineAcceptsSink:
    """TS-91-1: NightShiftEngine stores a provided SinkDispatcher."""

    def test_engine_accepts_sink_dispatcher(self) -> None:
        """NightShiftEngine stores the provided sink_dispatcher as _sink."""
        from agent_fox.nightshift.engine import NightShiftEngine

        mock_sink = MagicMock(spec=SinkDispatcher)
        config = _make_config()
        platform = MagicMock()

        # FAILS until __init__ accepts sink_dispatcher parameter
        engine = NightShiftEngine(config, platform, sink_dispatcher=mock_sink)

        assert engine._sink is mock_sink, "NightShiftEngine._sink must reference the provided SinkDispatcher"


# ---------------------------------------------------------------------------
# TS-91-2: NightShiftEngine defaults to None sink
# Requirement: 91-REQ-1.3
# ---------------------------------------------------------------------------


class TestEngineDefaultsNoneSink:
    """TS-91-2: NightShiftEngine works without a SinkDispatcher."""

    def test_engine_defaults_to_none_sink(self) -> None:
        """When no sink_dispatcher provided, engine._sink is None."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = _make_config()
        platform = MagicMock()

        engine = NightShiftEngine(config, platform)

        # FAILS until _sink attribute is added to NightShiftEngine
        assert engine._sink is None, "NightShiftEngine._sink must be None when no sink_dispatcher is provided"


# ---------------------------------------------------------------------------
# TS-91-3: CLI creates SinkDispatcher with DuckDBSink
# Requirement: 91-REQ-1.2
# ---------------------------------------------------------------------------


class TestCliCreatesSinkDispatcher:
    """TS-91-3: night_shift_cmd creates and passes SinkDispatcher to engine."""

    def test_cli_creates_sink_dispatcher_with_duckdb(self) -> None:
        """CLI creates a non-None SinkDispatcher backed by DuckDBSink."""
        from click.testing import CliRunner

        from agent_fox.cli.nightshift import night_shift_cmd
        from agent_fox.nightshift.daemon import DaemonState

        mock_state = DaemonState(total_cost=0.0, issues_fixed=0)

        with (
            patch("agent_fox.nightshift.engine.validate_night_shift_prerequisites"),
            patch("agent_fox.nightshift.platform_factory.create_platform", return_value=MagicMock()),
            patch("agent_fox.ui.display.create_theme"),
            patch("agent_fox.ui.progress.ProgressDisplay") as mock_progress_cls,
            patch("agent_fox.nightshift.daemon.DaemonRunner") as mock_runner_cls,
            patch("agent_fox.nightshift.streams.build_streams", return_value=[MagicMock()]),
            patch("agent_fox.nightshift.engine.NightShiftEngine") as mock_engine_cls,
            patch("agent_fox.nightshift.daemon.SharedBudget"),
            patch("agent_fox.engine.hot_load.discover_new_specs_gated", new_callable=AsyncMock, return_value=[]),
            # Mock open_knowledge_store so CLI can create a SinkDispatcher without a real DB
            patch("agent_fox.knowledge.db.open_knowledge_store", return_value=MagicMock()),
        ):
            mock_progress = MagicMock()
            mock_progress_cls.return_value = mock_progress

            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_state)
            mock_runner_cls.return_value = mock_runner

            mock_engine = MagicMock()
            mock_engine.state.hunt_scans_completed = 0
            mock_engine.state.issues_fixed = 0
            mock_engine_cls.return_value = mock_engine

            runner = CliRunner()
            runner.invoke(
                night_shift_cmd,
                [],
                obj={"config": _make_config_for_cli(), "quiet": False},
                catch_exceptions=False,
            )

            call_kwargs = mock_engine_cls.call_args.kwargs
            # FAILS until CLI passes sink_dispatcher to NightShiftEngine
            assert "sink_dispatcher" in call_kwargs, "night_shift_cmd must pass sink_dispatcher= to NightShiftEngine"
            assert call_kwargs["sink_dispatcher"] is not None, (
                "sink_dispatcher must be a non-None SinkDispatcher backed by DuckDBSink"
            )


# ---------------------------------------------------------------------------
# TS-91-4: FixPipeline accepts SinkDispatcher
# Requirement: 91-REQ-2.2
# ---------------------------------------------------------------------------


class TestFixPipelineAcceptsSink:
    """TS-91-4: FixPipeline stores a provided SinkDispatcher."""

    def test_pipeline_accepts_sink_dispatcher(self) -> None:
        """FixPipeline stores sink_dispatcher as _sink."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        mock_sink = MagicMock(spec=SinkDispatcher)
        config = _make_config()
        platform = MagicMock()

        # FAILS until __init__ accepts sink_dispatcher parameter
        pipeline = FixPipeline(config, platform, sink_dispatcher=mock_sink)

        assert pipeline._sink is mock_sink, "FixPipeline._sink must reference the provided SinkDispatcher"


# ---------------------------------------------------------------------------
# TS-91-5: process_issue generates unique run_id
# Requirement: 91-REQ-2.1
# ---------------------------------------------------------------------------


class TestProcessIssueGeneratesRunId:
    """TS-91-5: Each process_issue invocation generates a fresh run_id."""

    @pytest.mark.asyncio
    async def test_process_issue_generates_unique_run_ids(self) -> None:
        """Two successive process_issue calls produce two distinct run_ids."""
        from agent_fox.knowledge.audit import generate_run_id as real_generate_run_id
        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.protocol import IssueResult

        config = _make_config()
        mock_platform = AsyncMock()
        pipeline = FixPipeline(config, mock_platform)

        captured_ids: list[str] = []

        def _capturing_generate() -> str:
            rid = real_generate_run_id()
            captured_ids.append(rid)
            return rid

        issue1 = IssueResult(number=1, title="Issue 1", html_url="http://example.com/1")
        issue2 = IssueResult(number=2, title="Issue 2", html_url="http://example.com/2")

        with (
            patch.object(pipeline, "_setup_workspace", AsyncMock(return_value=_mock_workspace())),
            patch.object(pipeline, "_cleanup_workspace", AsyncMock()),
            patch.object(pipeline, "_run_triage", AsyncMock(return_value=MagicMock(criteria=[], summary=""))),
            patch.object(pipeline, "_coder_review_loop", AsyncMock(return_value=False)),
            # Intercept generate_run_id in the nightshift.fix_pipeline module
            # (create=True so the patch works before the import is added)
            patch(
                "agent_fox.nightshift.fix_pipeline.generate_run_id",
                side_effect=_capturing_generate,
                create=True,
            ),
        ):
            await pipeline.process_issue(issue1, issue_body="fix bug 1")
            await pipeline.process_issue(issue2, issue_body="fix bug 2")

        # FAILS until process_issue calls generate_run_id
        assert len(captured_ids) == 2, (
            f"Expected generate_run_id to be called once per process_issue, got {len(captured_ids)} calls"
        )
        assert len(set(captured_ids)) == 2, "Each process_issue call must generate a distinct run_id"


# ---------------------------------------------------------------------------
# TS-91-6: _run_session passes sink and run_id to run_session
# Requirement: 91-REQ-3.3
# ---------------------------------------------------------------------------


class TestRunSessionPassesSinkAndRunId:
    """TS-91-6: FixPipeline._run_session forwards sink_dispatcher and run_id."""

    @pytest.mark.asyncio
    async def test_run_session_passes_sink_and_run_id(self) -> None:
        """_run_session calls run_session() with sink_dispatcher and run_id."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        mock_sink = MagicMock(spec=SinkDispatcher)
        config = _make_config()
        mock_platform = AsyncMock()

        # FAILS at construction if FixPipeline doesn't accept sink_dispatcher
        pipeline = FixPipeline(config, mock_platform, sink_dispatcher=mock_sink)
        # Also set _run_id directly since process_issue normally sets it
        pipeline._run_id = "test-run-id"  # type: ignore[attr-defined]

        mock_outcome = _mock_session_outcome()

        with patch(
            "agent_fox.session.session.run_session",
            new_callable=AsyncMock,
            return_value=mock_outcome,
        ) as mock_rs:
            await pipeline._run_session("coder", _mock_workspace(), spec=_mock_spec())

        call_kwargs = mock_rs.call_args.kwargs
        # FAILS until _run_session passes sink_dispatcher=
        assert call_kwargs.get("sink_dispatcher") is mock_sink, (
            "_run_session must pass sink_dispatcher to run_session()"
        )
        # FAILS until _run_session passes run_id=
        assert call_kwargs.get("run_id") == "test-run-id", "_run_session must pass run_id to run_session()"


# ---------------------------------------------------------------------------
# TS-91-7: session.complete emitted after successful fix session
# Requirement: 91-REQ-3.1
# ---------------------------------------------------------------------------


class TestSessionCompleteEmitted:
    """TS-91-7: session.complete audit event emitted after successful session."""

    @pytest.mark.asyncio
    async def test_session_complete_emitted_after_triage(self) -> None:
        """_run_triage emits session.complete with archetype, cost, tokens."""
        from agent_fox.knowledge.audit import AuditEventType
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        mock_sink = MagicMock(spec=SinkDispatcher)
        config = _make_config()
        mock_platform = AsyncMock()

        # FAILS at construction until sink_dispatcher is added
        pipeline = FixPipeline(config, mock_platform, sink_dispatcher=mock_sink)
        pipeline._run_id = "test-run-id"  # type: ignore[attr-defined]

        mock_outcome = _mock_session_outcome(input_tokens=1000, output_tokens=200)

        with (
            patch.object(pipeline, "_run_session", AsyncMock(return_value=mock_outcome)),
            patch(
                "agent_fox.nightshift.fix_pipeline.emit_audit_event",
                create=True,
            ) as mock_emit,
        ):
            await pipeline._run_triage(_mock_spec(), _mock_workspace())

        # FAILS until _run_triage emits session.complete
        complete_calls = [
            c for c in mock_emit.call_args_list if len(c.args) >= 3 and c.args[2] == AuditEventType.SESSION_COMPLETE
        ]
        assert len(complete_calls) >= 1, "_run_triage must emit session.complete after a successful triage session"

        payload = complete_calls[0].kwargs.get("payload", {})
        assert payload.get("archetype") == "triage", "session.complete payload must include archetype='triage'"
        assert isinstance(payload.get("cost"), float) and payload["cost"] >= 0, (
            "session.complete payload must include a non-negative cost"
        )
        assert payload.get("input_tokens", 0) > 0, "session.complete payload must include input_tokens > 0"


# ---------------------------------------------------------------------------
# TS-91-8: session.fail emitted after failed fix session
# Requirement: 91-REQ-3.2
# ---------------------------------------------------------------------------


class TestSessionFailEmitted:
    """TS-91-8: session.fail audit event emitted when _run_session raises."""

    @pytest.mark.asyncio
    async def test_session_fail_emitted_when_triage_raises(self) -> None:
        """session.fail with error_message emitted when _run_session raises."""
        from agent_fox.knowledge.audit import AuditEventType
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        mock_sink = MagicMock(spec=SinkDispatcher)
        config = _make_config()
        mock_platform = AsyncMock()

        # FAILS at construction until sink_dispatcher is added
        pipeline = FixPipeline(config, mock_platform, sink_dispatcher=mock_sink)
        pipeline._run_id = "test-run-id"  # type: ignore[attr-defined]

        with (
            patch.object(
                pipeline,
                "_run_session",
                AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch(
                "agent_fox.nightshift.fix_pipeline.emit_audit_event",
                create=True,
            ) as mock_emit,
        ):
            # _run_triage catches exceptions and returns empty TriageResult
            await pipeline._run_triage(_mock_spec(), _mock_workspace())

        # FAILS until session.fail is emitted on _run_session exception
        fail_calls = [
            c for c in mock_emit.call_args_list if len(c.args) >= 3 and c.args[2] == AuditEventType.SESSION_FAIL
        ]
        assert len(fail_calls) >= 1, "_run_triage must emit session.fail when _run_session raises"
        payload = fail_calls[0].kwargs.get("payload", {})
        assert "boom" in payload.get("error_message", ""), "session.fail payload must include the error_message"


# ---------------------------------------------------------------------------
# TS-91-9: emit_auxiliary_cost emits session.complete
# Requirements: 91-REQ-4.1, 91-REQ-4.2, 91-REQ-4.3, 91-REQ-4.4
# ---------------------------------------------------------------------------


class TestEmitAuxiliaryCost:
    """TS-91-9: emit_auxiliary_cost emits session.complete with correct payload."""

    def test_emit_auxiliary_cost_session_complete(self) -> None:
        """emit_auxiliary_cost emits SESSION_COMPLETE with archetype and cost."""
        # FAILS with ModuleNotFoundError until cost_helpers.py is created
        from agent_fox.knowledge.audit import AuditEventType
        from agent_fox.nightshift.cost_helpers import emit_auxiliary_cost  # type: ignore[import]

        mock_sink = MagicMock(spec=SinkDispatcher)

        # Mock API response with known token counts
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.cache_creation_input_tokens = 0

        mock_pricing = MagicMock()
        mock_pricing.models = {}

        with patch(
            "agent_fox.engine.audit_helpers.emit_audit_event",
        ) as mock_emit:
            emit_auxiliary_cost(
                mock_sink,
                "run-1",
                "hunt_critic",
                mock_response,
                "claude-opus-4-5",
                mock_pricing,
            )

        payload = mock_emit.call_args.kwargs.get("payload", {})
        assert payload.get("archetype") == "hunt_critic"
        assert payload.get("input_tokens") == 100
        assert payload.get("output_tokens") == 50
        assert isinstance(payload.get("cost"), float)
        assert mock_emit.call_args.args[2] == AuditEventType.SESSION_COMPLETE


# ---------------------------------------------------------------------------
# TS-91-10: emit_auxiliary_cost is no-op when sink is None
# Requirement: 91-REQ-4.E1
# ---------------------------------------------------------------------------


class TestEmitAuxiliaryCostNoopNoneSink:
    """TS-91-10: emit_auxiliary_cost is a no-op when sink is None."""

    def test_emit_auxiliary_cost_noop_when_sink_none(self) -> None:
        """No exception and no event when sink_dispatcher is None."""
        # FAILS with ModuleNotFoundError until cost_helpers.py is created
        from agent_fox.nightshift.cost_helpers import emit_auxiliary_cost  # type: ignore[import]

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.cache_creation_input_tokens = 0

        mock_pricing = MagicMock()
        mock_pricing.models = {}

        # Must not raise
        emit_auxiliary_cost(
            None,
            "run-1",
            "hunt_critic",
            mock_response,
            "claude-opus-4-5",
            mock_pricing,
        )


# ---------------------------------------------------------------------------
# TS-91-11: nightshift/audit.py module removed
# Requirement: 91-REQ-5.1
# ---------------------------------------------------------------------------


class TestJsonlAuditModuleRemoved:
    """TS-91-11: The JSONL-based nightshift/audit.py module no longer exists."""

    def test_nightshift_audit_module_does_not_exist(self) -> None:
        """agent_fox/nightshift/audit.py must be absent."""
        audit_path = Path("agent_fox/nightshift/audit.py")
        # FAILS because the file currently exists
        assert not audit_path.exists(), (
            "agent_fox/nightshift/audit.py must be removed (91-REQ-5.1). "
            "Route all audit events through the standard DuckDB pipeline."
        )


# ---------------------------------------------------------------------------
# TS-91-12: NightShiftEngine uses standard emit_audit_event
# Requirements: 91-REQ-5.2, 91-REQ-5.3
# ---------------------------------------------------------------------------


class TestEngineUsesStandardAudit:
    """TS-91-12: engine.py imports from engine.audit_helpers, not nightshift.audit."""

    def test_engine_imports_standard_audit_helper(self) -> None:
        """engine.py must not import from nightshift.audit."""
        source = Path("agent_fox/nightshift/engine.py").read_text(encoding="utf-8")

        # FAILS because engine.py currently imports from nightshift.audit
        assert "from agent_fox.nightshift.audit" not in source, (
            "engine.py must not import from agent_fox.nightshift.audit (that module is being removed)"
        )
        assert "from agent_fox.engine.audit_helpers" in source, (
            "engine.py must import emit_audit_event from agent_fox.engine.audit_helpers"
        )


# ---------------------------------------------------------------------------
# TS-91-13: DaemonRunner uses standard emit_audit_event
# Requirement: 91-REQ-5.3
# ---------------------------------------------------------------------------


class TestDaemonUsesStandardAudit:
    """TS-91-13: daemon.py must not import from nightshift.audit."""

    def test_daemon_does_not_import_nightshift_audit(self) -> None:
        """daemon.py must not import from the removed nightshift.audit module."""
        source = Path("agent_fox/nightshift/daemon.py").read_text(encoding="utf-8")

        # FAILS if daemon.py imports from nightshift.audit
        assert "from agent_fox.nightshift.audit" not in source, (
            "daemon.py must not import from agent_fox.nightshift.audit "
            "(that module is being removed — use engine.audit_helpers instead)"
        )


# ---------------------------------------------------------------------------
# TS-91-E1: DuckDB unavailable at startup
# Requirement: 91-REQ-1.E1
# ---------------------------------------------------------------------------


class TestCliDuckDBUnavailable:
    """TS-91-E1: When DuckDB cannot be opened, CLI proceeds without sink."""

    def test_cli_proceeds_without_sink_when_duckdb_fails(self) -> None:
        """If DuckDB open fails, CLI logs warning and uses sink_dispatcher=None."""
        from click.testing import CliRunner

        from agent_fox.cli.nightshift import night_shift_cmd
        from agent_fox.nightshift.daemon import DaemonState

        mock_state = DaemonState(total_cost=0.0, issues_fixed=0)

        with (
            patch("agent_fox.nightshift.engine.validate_night_shift_prerequisites"),
            patch("agent_fox.nightshift.platform_factory.create_platform", return_value=MagicMock()),
            patch("agent_fox.ui.display.create_theme"),
            patch("agent_fox.ui.progress.ProgressDisplay") as mock_progress_cls,
            patch("agent_fox.nightshift.daemon.DaemonRunner") as mock_runner_cls,
            patch("agent_fox.nightshift.streams.build_streams", return_value=[MagicMock()]),
            patch("agent_fox.nightshift.engine.NightShiftEngine") as mock_engine_cls,
            patch("agent_fox.nightshift.daemon.SharedBudget"),
            patch("agent_fox.engine.hot_load.discover_new_specs_gated", new_callable=AsyncMock, return_value=[]),
            # Make DuckDB unavailable
            patch(
                "agent_fox.knowledge.db.open_knowledge_store",
                side_effect=Exception("db locked"),
                create=True,
            ) as mock_open_store,
        ):
            mock_progress = MagicMock()
            mock_progress_cls.return_value = mock_progress

            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_state)
            mock_runner_cls.return_value = mock_runner

            mock_engine = MagicMock()
            mock_engine.state.hunt_scans_completed = 0
            mock_engine.state.issues_fixed = 0
            mock_engine_cls.return_value = mock_engine

            runner = CliRunner()
            runner.invoke(
                night_shift_cmd,
                [],
                obj={"config": _make_config_for_cli(), "quiet": False},
                catch_exceptions=False,
            )

            # FAILS until CLI attempts to open DuckDB (no calls currently)
            assert mock_open_store.called, (
                "CLI must attempt to open DuckDB for audit — open_knowledge_store was never called"
            )

            # After DuckDB fails, engine must be created with sink_dispatcher=None
            assert mock_engine_cls.call_args.kwargs.get("sink_dispatcher") is None, (
                "When DuckDB is unavailable, NightShiftEngine must receive sink_dispatcher=None"
            )


# ---------------------------------------------------------------------------
# TS-91-E2: Audit write failure during fix session does not crash pipeline
# Requirement: 91-REQ-3.E1
# ---------------------------------------------------------------------------


class TestAuditWriteFailureContinues:
    """TS-91-E2: Fix pipeline continues even when audit event write fails."""

    @pytest.mark.asyncio
    async def test_pipeline_continues_despite_audit_write_failure(self) -> None:
        """process_issue returns FixMetrics even if sink.emit_audit_event raises."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.protocol import IssueResult

        mock_sink = MagicMock(spec=SinkDispatcher)
        mock_sink.emit_audit_event.side_effect = RuntimeError("write failed")
        config = _make_config()
        mock_platform = AsyncMock()

        # FAILS at construction until FixPipeline accepts sink_dispatcher
        pipeline = FixPipeline(config, mock_platform, sink_dispatcher=mock_sink)

        issue = IssueResult(number=99, title="Audit error test", html_url="http://example.com/99")

        with (
            patch.object(pipeline, "_setup_workspace", AsyncMock(return_value=_mock_workspace())),
            patch.object(pipeline, "_cleanup_workspace", AsyncMock()),
            patch.object(pipeline, "_run_triage", AsyncMock(return_value=MagicMock(criteria=[], summary=""))),
            patch.object(pipeline, "_coder_review_loop", AsyncMock(return_value=False)),
        ):
            metrics = await pipeline.process_issue(issue, issue_body="fix the audit error")

        # Pipeline must complete and return FixMetrics
        assert metrics is not None, "process_issue must return FixMetrics even on audit failure"
        assert metrics.sessions_run >= 0, "sessions_run must be non-negative"


# ---------------------------------------------------------------------------
# TS-91-E3: Empty run_id skips audit emission
# Requirements: 91-REQ-2.E1, 91-REQ-5.E1
# ---------------------------------------------------------------------------


class TestEmptyRunIdSkipsEmission:
    """TS-91-E3: emit_audit_event with empty run_id is a no-op (existing guard)."""

    def test_empty_run_id_does_not_emit(self) -> None:
        """Standard emit_audit_event returns without calling sink when run_id=''.

        This validates the existing guard in engine/audit_helpers.py which is
        the foundation for graceful degradation across all nightshift audit calls.
        """
        from agent_fox.engine.audit_helpers import emit_audit_event
        from agent_fox.knowledge.audit import AuditEventType

        mock_sink = MagicMock(spec=SinkDispatcher)

        # The existing guard: if sink is None or not run_id: return
        emit_audit_event(mock_sink, "", AuditEventType.SESSION_COMPLETE, payload={"cost": 1.0})

        assert mock_sink.emit_audit_event.call_count == 0, "emit_audit_event must not call sink when run_id is empty"
