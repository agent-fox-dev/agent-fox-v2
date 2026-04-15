"""Unit tests for fix command progress display.

Test Spec: TS-76-1 through TS-76-19, TS-76-E1 through TS-76-E5
Requirements: 76-REQ-1.1 through 76-REQ-6.E2
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from agent_fox.cli.fix import (
    _build_fix_session_runner,
    _build_improve_session_runner,
    fix_cmd,
)
from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.checks import CheckCategory, CheckDescriptor, run_checks
from agent_fox.fix.fix import FixResult, TerminationReason, run_fix_loop
from agent_fox.fix.improve import ImproveResult, ImproveTermination, run_improve_loop
from agent_fox.fix.spec_gen import FixSpec

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_check(name: str = "pytest") -> CheckDescriptor:
    """Create a CheckDescriptor with sensible defaults."""
    return CheckDescriptor(
        name=name,
        command=["uv", "run", name],
        category=CheckCategory.TEST,
    )


def _make_fix_result(
    reason: TerminationReason = TerminationReason.ALL_FIXED,
) -> FixResult:
    """Create a FixResult for test mocking."""
    return FixResult(
        passes_completed=1,
        clusters_resolved=1,
        clusters_remaining=0,
        sessions_consumed=0,
        termination_reason=reason,
        remaining_failures=[],
    )


def _make_improve_result() -> ImproveResult:
    """Create an ImproveResult for test mocking."""
    return ImproveResult(
        passes_completed=1,
        max_passes=3,
        total_improvements=0,
        improvements_by_tier={},
        verifier_pass_count=1,
        verifier_fail_count=0,
        sessions_consumed=3,
        total_cost=0.30,
        termination_reason=ImproveTermination.CONVERGED,
        pass_results=[],
    )


def _fake_asyncio_run(
    *,
    return_value: Any = None,
    side_effect: BaseException | None = None,
):
    """Build a side_effect for mocking ``asyncio.run`` that closes the coroutine.

    Without closing the coroutine, Python emits
    ``RuntimeWarning: coroutine '...' was never awaited``.
    """

    def _run(coro, **_kwargs: Any):
        coro.close()
        if side_effect is not None:
            raise side_effect
        return return_value

    return _run


def _make_cli_obj(
    config: AgentFoxConfig | None = None,
    *,
    json_mode: bool = False,
    quiet: bool = False,
) -> dict:
    """Build a Click context obj dict for invoking fix_cmd."""
    if config is None:
        config = AgentFoxConfig()
    return {"config": config, "json": json_mode, "quiet": quiet}


# ---------------------------------------------------------------------------
# Banner tests (TS-76-1, TS-76-2, TS-76-3)
# ---------------------------------------------------------------------------


class TestBannerRendering:
    """Banner rendering/suppression tests.

    Requirements: 76-REQ-1.1, 76-REQ-1.2, 76-REQ-1.3
    """

    def test_banner_rendered_in_normal_mode(self) -> None:
        """TS-76-1: render_banner is called when not quiet and not JSON mode.

        Requirement: 76-REQ-1.1
        """
        runner = CliRunner()
        mock_check = _make_check()

        with (
            patch(
                "agent_fox.cli.fix.detect_checks",
                return_value=[mock_check],
            ),
            patch(
                "agent_fox.cli.fix.asyncio.run",
                side_effect=_fake_asyncio_run(return_value=_make_fix_result()),
            ),
            patch(
                "agent_fox.cli.fix.render_banner",
                create=True,
            ) as mock_banner,
        ):
            runner.invoke(
                fix_cmd,
                [],
                obj=_make_cli_obj(quiet=False, json_mode=False),
                catch_exceptions=False,
            )

        assert mock_banner.call_count == 1, "render_banner should be called once in normal (non-quiet, non-JSON) mode"

    def test_banner_suppressed_in_quiet_mode(self) -> None:
        """TS-76-2: render_banner is NOT called when --quiet is active.

        Requirement: 76-REQ-1.2
        """
        runner = CliRunner()
        mock_check = _make_check()

        with (
            patch(
                "agent_fox.cli.fix.detect_checks",
                return_value=[mock_check],
            ),
            patch(
                "agent_fox.cli.fix.asyncio.run",
                side_effect=_fake_asyncio_run(return_value=_make_fix_result()),
            ),
            patch(
                "agent_fox.cli.fix.render_banner",
                create=True,
            ) as mock_banner,
        ):
            runner.invoke(
                fix_cmd,
                [],
                obj=_make_cli_obj(quiet=True, json_mode=False),
                catch_exceptions=False,
            )

        assert mock_banner.call_count == 0, "render_banner should NOT be called in quiet mode"

    def test_banner_suppressed_in_json_mode(self) -> None:
        """TS-76-3: render_banner is NOT called when JSON mode is active.

        Requirement: 76-REQ-1.3
        """
        runner = CliRunner()
        mock_check = _make_check()

        with (
            patch(
                "agent_fox.cli.fix.detect_checks",
                return_value=[mock_check],
            ),
            patch(
                "agent_fox.cli.fix.asyncio.run",
                side_effect=_fake_asyncio_run(return_value=_make_fix_result()),
            ),
            patch(
                "agent_fox.cli.fix.render_banner",
                create=True,
            ) as mock_banner,
        ):
            result = runner.invoke(
                fix_cmd,
                [],
                obj=_make_cli_obj(quiet=False, json_mode=True),
                catch_exceptions=False,
            )
            # Suppress unused variable warning
            _ = result

        assert mock_banner.call_count == 0, "render_banner should NOT be called in JSON mode"


# ---------------------------------------------------------------------------
# ProgressDisplay lifecycle tests (TS-76-4, TS-76-5, TS-76-6)
# ---------------------------------------------------------------------------


class TestProgressDisplayLifecycle:
    """ProgressDisplay lifecycle tests.

    Requirements: 76-REQ-2.1, 76-REQ-2.2, 76-REQ-2.3
    """

    def test_progress_display_created_and_started(self) -> None:
        """TS-76-4: ProgressDisplay is created and start() is called.

        Requirement: 76-REQ-2.1
        """
        runner = CliRunner()
        mock_check = _make_check()

        with (
            patch(
                "agent_fox.cli.fix.detect_checks",
                return_value=[mock_check],
            ),
            patch(
                "agent_fox.cli.fix.asyncio.run",
                side_effect=_fake_asyncio_run(return_value=_make_fix_result()),
            ),
            patch(
                "agent_fox.cli.fix.ProgressDisplay",
                create=True,
            ) as mock_pd_cls,
        ):
            runner.invoke(
                fix_cmd,
                [],
                obj=_make_cli_obj(),
                catch_exceptions=False,
            )

        assert mock_pd_cls.call_count == 1, "ProgressDisplay should be created once"
        assert mock_pd_cls.return_value.start.call_count == 1, "start() should be called once before the fix loop"

    def test_progress_display_stopped_on_error(self) -> None:
        """TS-76-5: stop() is called even when an exception occurs.

        Requirement: 76-REQ-2.2
        """
        runner = CliRunner()
        mock_check = _make_check()

        with (
            patch(
                "agent_fox.cli.fix.detect_checks",
                return_value=[mock_check],
            ),
            patch(
                "agent_fox.cli.fix.asyncio.run",
                side_effect=_fake_asyncio_run(side_effect=RuntimeError("Simulated error")),
            ),
            patch(
                "agent_fox.cli.fix.ProgressDisplay",
                create=True,
            ) as mock_pd_cls,
        ):
            runner.invoke(
                fix_cmd,
                [],
                obj=_make_cli_obj(),
                catch_exceptions=True,
            )

        assert mock_pd_cls.return_value.stop.call_count == 1, (
            "stop() should be called exactly once even after an exception"
        )

    def test_progress_display_quiet_when_quiet_mode(self) -> None:
        """TS-76-6: ProgressDisplay is created with quiet=True in quiet mode.

        Requirement: 76-REQ-2.3
        """
        runner = CliRunner()
        mock_check = _make_check()

        with (
            patch(
                "agent_fox.cli.fix.detect_checks",
                return_value=[mock_check],
            ),
            patch(
                "agent_fox.cli.fix.asyncio.run",
                side_effect=_fake_asyncio_run(return_value=_make_fix_result()),
            ),
            patch(
                "agent_fox.cli.fix.ProgressDisplay",
                create=True,
            ) as mock_pd_cls,
        ):
            runner.invoke(
                fix_cmd,
                [],
                obj=_make_cli_obj(quiet=True),
                catch_exceptions=False,
            )

        assert mock_pd_cls.call_count == 1
        _, kwargs = mock_pd_cls.call_args
        assert kwargs.get("quiet") is True, "ProgressDisplay should be created with quiet=True when quiet mode is on"

    def test_progress_display_quiet_when_json_mode(self) -> None:
        """TS-76-6 (JSON variant): ProgressDisplay is quiet=True in JSON mode.

        Requirement: 76-REQ-2.3
        """
        runner = CliRunner()
        mock_check = _make_check()

        with (
            patch(
                "agent_fox.cli.fix.detect_checks",
                return_value=[mock_check],
            ),
            patch(
                "agent_fox.cli.fix.asyncio.run",
                side_effect=_fake_asyncio_run(return_value=_make_fix_result()),
            ),
            patch(
                "agent_fox.cli.fix.ProgressDisplay",
                create=True,
            ) as mock_pd_cls,
        ):
            runner.invoke(
                fix_cmd,
                [],
                obj=_make_cli_obj(json_mode=True),
                catch_exceptions=False,
            )

        assert mock_pd_cls.call_count == 1
        _, kwargs = mock_pd_cls.call_args
        assert kwargs.get("quiet") is True, "ProgressDisplay should be created with quiet=True when JSON mode is on"


# ---------------------------------------------------------------------------
# Activity callback wiring tests (TS-76-7, TS-76-8)
# ---------------------------------------------------------------------------


class TestActivityCallbackWiring:
    """Activity callback forwarding to run_session.

    Requirements: 76-REQ-3.1, 76-REQ-3.2
    """

    @pytest.mark.asyncio
    async def test_fix_session_runner_passes_activity_callback(self, tmp_path: Path) -> None:
        """TS-76-7: Fix session runner forwards activity_callback to run_session.

        Requirement: 76-REQ-3.1
        """
        config = AgentFoxConfig()
        activity_cb = MagicMock()

        mock_outcome = MagicMock()
        mock_outcome.input_tokens = 100
        mock_outcome.output_tokens = 50
        mock_outcome.output = "done"

        mock_fix_spec = MagicMock(spec=FixSpec)
        mock_fix_spec.cluster_label = "test_cluster"
        mock_fix_spec.task_prompt = "Fix this"

        with patch("agent_fox.cli.fix.run_session", new_callable=AsyncMock) as mock_run_session:
            mock_run_session.return_value = mock_outcome
            # _build_fix_session_runner must accept activity_callback
            runner = _build_fix_session_runner(config, tmp_path, activity_callback=activity_cb)
            await runner(mock_fix_spec)

        assert mock_run_session.called, "run_session should have been called"
        call_kwargs = mock_run_session.call_args.kwargs
        assert call_kwargs.get("activity_callback") is activity_cb, (
            "run_session should receive the activity_callback from the session runner"
        )

    @pytest.mark.asyncio
    async def test_improve_session_runner_passes_activity_callback(self, tmp_path: Path) -> None:
        """TS-76-8: Improve session runner forwards activity_callback to run_session.

        Requirement: 76-REQ-3.2
        """
        config = AgentFoxConfig()
        activity_cb = MagicMock()

        mock_outcome = MagicMock()
        mock_outcome.input_tokens = 100
        mock_outcome.output_tokens = 50
        mock_outcome.output = "{}"

        with patch("agent_fox.cli.fix.run_session", new_callable=AsyncMock) as mock_run_session:
            mock_run_session.return_value = mock_outcome
            # _build_improve_session_runner must accept activity_callback
            runner = _build_improve_session_runner(config, tmp_path, activity_callback=activity_cb)
            await runner("sys prompt", "task prompt", "STANDARD")

        assert mock_run_session.called, "run_session should have been called"
        call_kwargs = mock_run_session.call_args.kwargs
        assert call_kwargs.get("activity_callback") is activity_cb, (
            "run_session should receive the activity_callback from the improve runner"
        )


# ---------------------------------------------------------------------------
# Fix loop event emission tests (TS-76-9 through TS-76-12)
# ---------------------------------------------------------------------------


class TestFixLoopProgressEvents:
    """Fix loop emits FixProgressEvent at key lifecycle points.

    Requirements: 76-REQ-4.1, 76-REQ-4.2, 76-REQ-4.3, 76-REQ-4.4
    """

    @pytest.mark.asyncio
    async def test_fix_loop_emits_pass_start_event(self, tmp_path: Path) -> None:
        """TS-76-9: run_fix_loop emits checks_start at the beginning of each pass.

        Requirement: 76-REQ-4.1
        """
        config = AgentFoxConfig()
        callback = MagicMock()
        mock_check = _make_check()

        with (
            patch("agent_fox.fix.fix.detect_checks", return_value=[mock_check]),
            patch(
                "agent_fox.fix.fix.run_checks",
                return_value=([], [mock_check]),
            ),
        ):
            # progress_callback parameter must exist in run_fix_loop
            result = await run_fix_loop(
                tmp_path,
                config,
                max_passes=1,
                progress_callback=callback,
            )

        start_calls = [c for c in callback.call_args_list if c.args[0].stage == "checks_start"]
        assert len(start_calls) >= 1, "progress_callback should be called with stage='checks_start'"
        assert start_calls[0].args[0].pass_number == 1
        assert start_calls[0].args[0].phase == "repair"
        _ = result

    @pytest.mark.asyncio
    async def test_fix_loop_emits_all_passed_event(self, tmp_path: Path) -> None:
        """TS-76-10: run_fix_loop emits an all_passed event when checks pass.

        Requirement: 76-REQ-4.2
        """
        config = AgentFoxConfig()
        callback = MagicMock()
        mock_check = _make_check()

        with (
            patch("agent_fox.fix.fix.detect_checks", return_value=[mock_check]),
            patch(
                "agent_fox.fix.fix.run_checks",
                return_value=([], [mock_check]),
            ),
        ):
            await run_fix_loop(
                tmp_path,
                config,
                max_passes=1,
                progress_callback=callback,
            )

        stages = {c.args[0].stage for c in callback.call_args_list}
        assert "all_passed" in stages, "progress_callback should be called with stage='all_passed' when all checks pass"

    @pytest.mark.asyncio
    async def test_fix_loop_emits_clusters_found_event(self, tmp_path: Path) -> None:
        """TS-76-11: run_fix_loop emits clusters_found event with count in detail.

        Requirement: 76-REQ-4.3
        """
        config = AgentFoxConfig()
        callback = MagicMock()
        mock_check = _make_check()

        from agent_fox.fix.checks import FailureRecord
        from agent_fox.fix.clusterer import FailureCluster

        failure = FailureRecord(check=mock_check, output="FAILED test", exit_code=1)
        cluster = FailureCluster(
            label="test failure cluster",
            failures=[failure],
            suggested_approach="Fix it",
        )

        mock_spec = MagicMock()
        mock_spec.task_prompt = "fix it"
        mock_spec.spec_dir = tmp_path / "fix_specs"

        with (
            patch("agent_fox.fix.fix.detect_checks", return_value=[mock_check]),
            patch(
                "agent_fox.fix.fix.run_checks",
                side_effect=[([failure], []), ([], [mock_check])],
            ),
            patch(
                "agent_fox.fix.fix.cluster_failures",
                return_value=[cluster],
            ),
            patch("agent_fox.fix.fix.generate_fix_spec", return_value=mock_spec),
            patch("agent_fox.fix.fix.cleanup_fix_specs"),
        ):
            await run_fix_loop(
                tmp_path,
                config,
                max_passes=2,
                progress_callback=callback,
            )

        cluster_calls = [c for c in callback.call_args_list if c.args[0].stage == "clusters_found"]
        assert len(cluster_calls) >= 1, "progress_callback should be called with stage='clusters_found'"
        assert "1" in cluster_calls[0].args[0].detail, "detail should contain the cluster count"

    @pytest.mark.asyncio
    async def test_fix_loop_emits_session_start_event(self, tmp_path: Path) -> None:
        """TS-76-12: run_fix_loop emits session_start event with cluster label.

        Requirement: 76-REQ-4.4
        """
        config = AgentFoxConfig()
        callback = MagicMock()
        mock_check = _make_check()

        from agent_fox.fix.checks import FailureRecord
        from agent_fox.fix.clusterer import FailureCluster

        failure = FailureRecord(check=mock_check, output="FAILED", exit_code=1)
        cluster = FailureCluster(
            label="auth_error_cluster",
            failures=[failure],
            suggested_approach="Fix authentication",
        )

        mock_spec = MagicMock()
        mock_spec.task_prompt = "fix auth"
        mock_spec.spec_dir = tmp_path / "fix_specs"

        async def mock_session_runner(fix_spec: FixSpec) -> float:
            return 0.05

        with (
            patch("agent_fox.fix.fix.detect_checks", return_value=[mock_check]),
            patch(
                "agent_fox.fix.fix.run_checks",
                side_effect=[([failure], []), ([], [mock_check])],
            ),
            patch(
                "agent_fox.fix.fix.cluster_failures",
                return_value=[cluster],
            ),
            patch("agent_fox.fix.fix.generate_fix_spec", return_value=mock_spec),
            patch("agent_fox.fix.fix.cleanup_fix_specs"),
        ):
            await run_fix_loop(
                tmp_path,
                config,
                max_passes=2,
                session_runner=mock_session_runner,
                progress_callback=callback,
            )

        session_calls = [c for c in callback.call_args_list if c.args[0].stage == "session_start"]
        assert len(session_calls) >= 1, "progress_callback should be called with stage='session_start'"
        assert session_calls[0].args[0].detail != "", "session_start detail should contain the cluster label"


# ---------------------------------------------------------------------------
# Improve loop event emission tests (TS-76-13, TS-76-14)
# ---------------------------------------------------------------------------


class TestImproveLoopProgressEvents:
    """Improve loop emits FixProgressEvent at key lifecycle points.

    Requirements: 76-REQ-4.5, 76-REQ-4.6
    """

    @pytest.mark.asyncio
    async def test_improve_loop_emits_analyzer_start_event(self, tmp_path: Path) -> None:
        """TS-76-13: run_improve_loop emits analyzer_start at the start of each pass.

        Requirement: 76-REQ-4.5
        """
        config = AgentFoxConfig()
        callback = MagicMock()

        # Mock improve loop to return early (budget too tight)
        async def mock_runner(sys_prompt: str, task_prompt: str, tier: str) -> tuple[float, str]:
            payload = '{"improvements": [], "summary": "none", "diminishing_returns": true}'
            return (100.0, payload)

        with (
            patch("agent_fox.fix.improve.query_oracle_context", return_value=""),
            patch("agent_fox.fix.improve.load_review_context", return_value=""),
            patch("agent_fox.fix.improve.parse_analyzer_response") as mock_parse,
        ):
            from agent_fox.fix.analyzer import AnalyzerResult

            mock_parse.return_value = AnalyzerResult(
                improvements=[],
                summary="No improvements",
                diminishing_returns=True,
                raw_response="{}",
            )
            # progress_callback parameter must exist in run_improve_loop
            await run_improve_loop(
                tmp_path,
                config,
                max_passes=1,
                session_runner=mock_runner,
                progress_callback=callback,
            )

        calls = [c for c in callback.call_args_list if c.args[0].stage == "analyzer_start"]
        assert len(calls) >= 1, "progress_callback should be called with stage='analyzer_start'"
        assert calls[0].args[0].phase == "improve", "improve loop events should have phase='improve'"

    @pytest.mark.asyncio
    async def test_improve_loop_emits_session_role_events(self, tmp_path: Path) -> None:
        """TS-76-14: run_improve_loop emits role events for analyzer/coder/verifier.

        Requirement: 76-REQ-4.6
        """
        import json

        config = AgentFoxConfig()
        callback = MagicMock()

        verifier_pass_json = json.dumps(
            {
                "quality_gates": "PASS",
                "improvement_valid": True,
                "verdict": "PASS",
                "evidence": "All good.",
            }
        )

        call_count = [0]

        async def mock_runner(sys_prompt: str, task_prompt: str, tier: str) -> tuple[float, str]:
            call_count[0] += 1
            if call_count[0] == 1:
                # Analyzer response with diminishing returns to stop after 1 pass
                return (
                    0.05,
                    '{"improvements": [], "summary": "done", "diminishing_returns": true}',
                )
            return (0.05, verifier_pass_json)

        with (
            patch("agent_fox.fix.improve.query_oracle_context", return_value=""),
            patch("agent_fox.fix.improve.load_review_context", return_value=""),
        ):
            await run_improve_loop(
                tmp_path,
                config,
                max_passes=1,
                session_runner=mock_runner,
                progress_callback=callback,
            )

        stages = {c.args[0].stage for c in callback.call_args_list}
        # At minimum, analyzer_start should appear
        assert "analyzer_start" in stages or "analyzer_done" in stages, "improve loop should emit analyzer phase events"


# ---------------------------------------------------------------------------
# Check callback event tests (TS-76-15, TS-76-16)
# ---------------------------------------------------------------------------


class TestCheckCallbackEvents:
    """Check callback is fired before and after each check.

    Requirements: 76-REQ-5.1, 76-REQ-5.2
    """

    def test_check_callback_called_on_start(self, tmp_path: Path) -> None:
        """TS-76-15: run_checks calls check_callback with stage='start' per check.

        Requirement: 76-REQ-5.1
        """
        checks = [_make_check("ruff"), _make_check("pytest")]
        callback = MagicMock()

        with patch("agent_fox.fix.checks.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            # check_callback parameter must exist in run_checks
            run_checks(checks, tmp_path, check_callback=callback)

        start_calls = [c for c in callback.call_args_list if c.args[0].stage == "start"]
        assert len(start_calls) == 2, "check_callback should be called with stage='start' once per check"

    def test_check_callback_called_on_done(self, tmp_path: Path) -> None:
        """TS-76-16: run_checks calls check_callback with stage='done' after each check.

        Requirement: 76-REQ-5.2
        """
        checks = [_make_check("ruff"), _make_check("pytest")]
        callback = MagicMock()

        with patch("agent_fox.fix.checks.subprocess.run") as mock_run:
            # First check passes, second fails
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=1, stdout="error", stderr=""),
            ]
            # check_callback parameter must exist in run_checks
            run_checks(checks, tmp_path, check_callback=callback)

        done_calls = [c for c in callback.call_args_list if c.args[0].stage == "done"]
        assert len(done_calls) == 2, "check_callback should be called with stage='done' once per check"
        pass_results = {c.args[0].passed for c in done_calls}
        assert pass_results == {True, False}, "done events should include both passed=True and passed=False"


# ---------------------------------------------------------------------------
# Signature inspection tests (TS-76-17, TS-76-18, TS-76-19)
# ---------------------------------------------------------------------------


class TestSignatures:
    """Verify callback parameters exist in function signatures.

    Requirements: 76-REQ-6.1, 76-REQ-6.2, 76-REQ-6.3
    """

    def test_run_fix_loop_has_progress_callback_parameter(self) -> None:
        """TS-76-17: run_fix_loop signature includes progress_callback parameter.

        Requirement: 76-REQ-6.1
        """
        sig = inspect.signature(run_fix_loop)
        assert "progress_callback" in sig.parameters, "run_fix_loop must have a progress_callback parameter"

    def test_run_improve_loop_has_progress_callback_parameter(self) -> None:
        """TS-76-18: run_improve_loop signature includes progress_callback parameter.

        Requirement: 76-REQ-6.2
        """
        sig = inspect.signature(run_improve_loop)
        assert "progress_callback" in sig.parameters, "run_improve_loop must have a progress_callback parameter"

    def test_run_checks_has_check_callback_parameter(self) -> None:
        """TS-76-19: run_checks signature includes check_callback parameter.

        Requirement: 76-REQ-6.3
        """
        sig = inspect.signature(run_checks)
        assert "check_callback" in sig.parameters, "run_checks must have a check_callback parameter"


# ---------------------------------------------------------------------------
# Edge case tests (TS-76-E1 through TS-76-E5)
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for progress display.

    Requirements: 76-REQ-2.E1, 76-REQ-4.E1, 76-REQ-4.E2, 76-REQ-6.E1, 76-REQ-6.E2
    """

    def test_progress_display_stopped_on_keyboard_interrupt(self) -> None:
        """TS-76-E1: ProgressDisplay.stop() is called on KeyboardInterrupt.

        Requirement: 76-REQ-2.E1
        """
        runner = CliRunner()
        mock_check = _make_check()

        with (
            patch(
                "agent_fox.cli.fix.detect_checks",
                return_value=[mock_check],
            ),
            patch(
                "agent_fox.cli.fix.asyncio.run",
                side_effect=_fake_asyncio_run(side_effect=KeyboardInterrupt()),
            ),
            patch(
                "agent_fox.cli.fix.ProgressDisplay",
                create=True,
            ) as mock_pd_cls,
        ):
            runner.invoke(
                fix_cmd,
                [],
                obj=_make_cli_obj(),
                catch_exceptions=True,
            )

        assert mock_pd_cls.return_value.stop.call_count == 1, "stop() should be called even on KeyboardInterrupt"

    @pytest.mark.asyncio
    async def test_cost_limit_emits_cost_limit_event(self, tmp_path: Path) -> None:
        """TS-76-E2: cost_limit event is emitted when fix loop hits the cost limit.

        Requirement: 76-REQ-4.E1
        """
        from agent_fox.core.config import OrchestratorConfig

        config = AgentFoxConfig(orchestrator=OrchestratorConfig(max_cost=0.001))
        callback = MagicMock()
        mock_check = _make_check()

        from agent_fox.fix.checks import FailureRecord
        from agent_fox.fix.clusterer import FailureCluster

        failure = FailureRecord(check=mock_check, output="FAILED", exit_code=1)
        cluster = FailureCluster(
            label="expensive_fix",
            failures=[failure],
            suggested_approach="expensive",
        )

        mock_spec = MagicMock()
        mock_spec.task_prompt = "fix"
        mock_spec.spec_dir = tmp_path / "specs"

        async def expensive_runner(fix_spec: FixSpec) -> float:
            return 1.0  # Exceeds cost limit

        with (
            patch("agent_fox.fix.fix.detect_checks", return_value=[mock_check]),
            patch(
                "agent_fox.fix.fix.run_checks",
                return_value=([failure], []),
            ),
            patch(
                "agent_fox.fix.fix.cluster_failures",
                return_value=[cluster],
            ),
            patch("agent_fox.fix.fix.generate_fix_spec", return_value=mock_spec),
            patch("agent_fox.fix.fix.cleanup_fix_specs"),
        ):
            await run_fix_loop(
                tmp_path,
                config,
                max_passes=3,
                session_runner=expensive_runner,
                progress_callback=callback,
            )

        stages = {c.args[0].stage for c in callback.call_args_list}
        assert "cost_limit" in stages, "progress_callback should be called with stage='cost_limit'"

    @pytest.mark.asyncio
    async def test_session_error_emits_session_error_event(self, tmp_path: Path) -> None:
        """TS-76-E3: A session_error event is emitted when a fix session raises.

        Requirement: 76-REQ-4.E2
        """
        config = AgentFoxConfig()
        callback = MagicMock()
        mock_check = _make_check()

        from agent_fox.fix.checks import FailureRecord
        from agent_fox.fix.clusterer import FailureCluster

        failure = FailureRecord(check=mock_check, output="FAILED", exit_code=1)
        cluster = FailureCluster(
            label="bad_cluster",
            failures=[failure],
            suggested_approach="fix it",
        )

        mock_spec = MagicMock()
        mock_spec.task_prompt = "fix"
        mock_spec.spec_dir = tmp_path / "specs"

        failing_runner = AsyncMock(side_effect=RuntimeError("session failed"))

        with (
            patch("agent_fox.fix.fix.detect_checks", return_value=[mock_check]),
            patch(
                "agent_fox.fix.fix.run_checks",
                side_effect=[([failure], []), ([], [mock_check])],
            ),
            patch(
                "agent_fox.fix.fix.cluster_failures",
                return_value=[cluster],
            ),
            patch("agent_fox.fix.fix.generate_fix_spec", return_value=mock_spec),
            patch("agent_fox.fix.fix.cleanup_fix_specs"),
        ):
            await run_fix_loop(
                tmp_path,
                config,
                max_passes=2,
                session_runner=failing_runner,
                progress_callback=callback,
            )

        stages = {c.args[0].stage for c in callback.call_args_list}
        assert "session_error" in stages, "progress_callback should be called with stage='session_error' on exception"

    @pytest.mark.asyncio
    async def test_none_progress_callback_is_backward_compatible(self, tmp_path: Path) -> None:
        """TS-76-E4: run_fix_loop with progress_callback=None runs without errors.

        Requirement: 76-REQ-6.E1
        """
        config = AgentFoxConfig()
        mock_check = _make_check()

        with (
            patch("agent_fox.fix.fix.detect_checks", return_value=[mock_check]),
            patch(
                "agent_fox.fix.fix.run_checks",
                return_value=([], [mock_check]),
            ),
        ):
            # Should not raise; omitting progress_callback uses default (None)
            result = await run_fix_loop(tmp_path, config, max_passes=1)

        assert result.termination_reason == TerminationReason.ALL_FIXED

    def test_none_check_callback_is_backward_compatible(self, tmp_path: Path) -> None:
        """TS-76-E5: run_checks with check_callback=None works identically to before.

        Requirement: 76-REQ-6.E2
        """
        checks = [_make_check("ruff"), _make_check("pytest")]

        with patch("agent_fox.fix.checks.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            # Should not raise
            failures, passed = run_checks(checks, tmp_path, check_callback=None)

        assert isinstance(failures, list)
        assert isinstance(passed, list)
        assert len(failures) + len(passed) == len(checks)
