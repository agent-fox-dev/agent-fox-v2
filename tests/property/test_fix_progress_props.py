"""Property tests for fix command progress display.

Test Spec: TS-76-P1 through TS-76-P6
Properties: Property 1 through 6 from design.md
Requirements: 76-REQ-1.2, 76-REQ-1.3, 76-REQ-2.2, 76-REQ-2.3, 76-REQ-2.E1,
              76-REQ-3.1, 76-REQ-3.2, 76-REQ-5.1, 76-REQ-5.2,
              76-REQ-6.E1, 76-REQ-6.E2
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.cli.fix import (
    _build_fix_session_runner,
    _build_improve_session_runner,
    fix_cmd,
)
from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.checks import CheckCategory, CheckDescriptor, run_checks
from agent_fox.fix.fix import TerminationReason, run_fix_loop
from agent_fox.ui.display import create_theme
from agent_fox.ui.progress import ProgressDisplay

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_check(name: str = "pytest") -> CheckDescriptor:
    """Create a CheckDescriptor."""
    return CheckDescriptor(
        name=name,
        command=["uv", "run", name],
        category=CheckCategory.TEST,
    )


def _make_fix_result(reason: TerminationReason = TerminationReason.ALL_FIXED):  # type: ignore[no-untyped-def]
    """Create a FixResult for mocking."""
    from agent_fox.fix.fix import FixResult

    return FixResult(
        passes_completed=1,
        clusters_resolved=0,
        clusters_remaining=0,
        sessions_consumed=0,
        termination_reason=reason,
        remaining_failures=[],
    )


def _fake_asyncio_run(
    *,
    return_value: Any = None,
    side_effect: BaseException | None = None,
):
    """Build a side_effect for mocking ``asyncio.run`` that closes the coroutine."""

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
    """Build Click context obj dict."""
    if config is None:
        config = AgentFoxConfig()
    return {"config": config, "json": json_mode, "quiet": quiet}


# ---------------------------------------------------------------------------
# TS-76-P1: Quiet Mode Suppresses All Output
# ---------------------------------------------------------------------------


class TestQuietSuppressionInvariant:
    """TS-76-P1: ProgressDisplay is quiet when quiet OR json_mode is True.

    Property 1 from design.md
    Validates: 76-REQ-1.2, 76-REQ-1.3, 76-REQ-2.3
    """

    @pytest.mark.parametrize("quiet", [True, False])
    @pytest.mark.parametrize("json_mode", [True, False])
    def test_progress_display_quiet_flag_matches_expectation(
        self, quiet: bool, json_mode: bool, tmp_path: Path
    ) -> None:
        """ProgressDisplay is created with quiet=True when quiet OR json_mode is True.

        Requirement: 76-REQ-2.3
        """
        expected_quiet = quiet or json_mode
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
                obj=_make_cli_obj(quiet=quiet, json_mode=json_mode),
                catch_exceptions=True,
            )

        if mock_pd_cls.call_count > 0:
            _, kwargs = mock_pd_cls.call_args
            actual_quiet = kwargs.get("quiet", False)
            assert actual_quiet == expected_quiet, (
                f"With quiet={quiet}, json_mode={json_mode}: "
                f"expected ProgressDisplay quiet={expected_quiet}, "
                f"got quiet={actual_quiet}"
            )
        else:
            # ProgressDisplay was never created — that's a failure
            pytest.fail("ProgressDisplay was not created; it must be created in fix_cmd")

    def test_progress_display_quiet_property(self) -> None:
        """ProgressDisplay._quiet reflects the quiet parameter.

        Ensures the quiet flag is stored correctly in the display object.
        """
        config = AgentFoxConfig()
        theme = create_theme(config.theme)

        pd_quiet = ProgressDisplay(theme, quiet=True)
        assert pd_quiet._quiet is True

        pd_loud = ProgressDisplay(theme, quiet=False)
        assert pd_loud._quiet is False


# ---------------------------------------------------------------------------
# TS-76-P2: Display Lifecycle Completeness
# ---------------------------------------------------------------------------


class TestLifecycleCompleteness:
    """TS-76-P2: For any execution outcome, stop() is always called exactly once.

    Property 2 from design.md
    Validates: 76-REQ-2.2, 76-REQ-2.E1
    """

    @pytest.mark.parametrize(
        "side_effect",
        [
            None,  # Normal completion
            RuntimeError("unexpected error"),  # Exception
            KeyboardInterrupt(),  # Keyboard interrupt
        ],
        ids=["normal", "runtime_error", "keyboard_interrupt"],
    )
    def test_stop_always_called(self, side_effect: BaseException | None, tmp_path: Path) -> None:
        """stop() is called exactly once regardless of execution outcome.

        Requirement: 76-REQ-2.2, 76-REQ-2.E1
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
                side_effect=_fake_asyncio_run(
                    return_value=_make_fix_result() if side_effect is None else None,
                    side_effect=side_effect,
                ),
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

        effect_name = type(side_effect).__name__
        assert mock_pd_cls.return_value.stop.call_count == 1, (
            f"stop() should be called exactly once (side_effect={effect_name})"
        )


# ---------------------------------------------------------------------------
# TS-76-P3: Activity Callback Wiring
# ---------------------------------------------------------------------------


class TestCallbackWiringInvariant:
    """TS-76-P3: For any session runner built with an activity_callback, run_session
    receives that same callback.

    Property 3 from design.md
    Validates: 76-REQ-3.1, 76-REQ-3.2
    """

    @pytest.mark.parametrize(
        "callback",
        [None, MagicMock()],
        ids=["none_callback", "mock_callback"],
    )
    @pytest.mark.asyncio
    async def test_fix_runner_wires_callback(self, callback: MagicMock | None, tmp_path: Path) -> None:
        """For any activity_callback (None or real), run_session receives it.

        Requirement: 76-REQ-3.1
        """
        config = AgentFoxConfig()
        mock_outcome = MagicMock()
        mock_outcome.input_tokens = 100
        mock_outcome.output_tokens = 50
        mock_outcome.output = "done"

        mock_fix_spec = MagicMock()
        mock_fix_spec.cluster_label = "test"
        mock_fix_spec.task_prompt = "fix"

        with patch("agent_fox.cli.fix.run_session", new_callable=AsyncMock) as mock_run_session:
            mock_run_session.return_value = mock_outcome
            runner = _build_fix_session_runner(config, tmp_path, activity_callback=callback)
            await runner(mock_fix_spec)

        call_kwargs = mock_run_session.call_args.kwargs
        assert call_kwargs.get("activity_callback") is callback, (
            "run_session should receive the exact callback passed to the runner builder"
        )

    @pytest.mark.parametrize(
        "callback",
        [None, MagicMock()],
        ids=["none_callback", "mock_callback"],
    )
    @pytest.mark.asyncio
    async def test_improve_runner_wires_callback(self, callback: MagicMock | None, tmp_path: Path) -> None:
        """For any activity_callback, improve runner passes it to run_session.

        Requirement: 76-REQ-3.2
        """
        config = AgentFoxConfig()
        mock_outcome = MagicMock()
        mock_outcome.input_tokens = 100
        mock_outcome.output_tokens = 50
        mock_outcome.output = "{}"

        with patch("agent_fox.cli.fix.run_session", new_callable=AsyncMock) as mock_run_session:
            mock_run_session.return_value = mock_outcome
            runner = _build_improve_session_runner(config, tmp_path, activity_callback=callback)
            await runner("sys", "task", "STANDARD")

        call_kwargs = mock_run_session.call_args.kwargs
        assert call_kwargs.get("activity_callback") is callback, (
            "improve runner should wire activity_callback through to run_session"
        )


# ---------------------------------------------------------------------------
# TS-76-P4: Callback Backward Compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """TS-76-P4: None callbacks produce no errors and valid return values.

    Property 4 from design.md
    Validates: 76-REQ-6.E1, 76-REQ-6.E2
    """

    @given(n_checks=st.integers(min_value=0, max_value=3))
    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_run_checks_none_callback_backward_compatible(self, n_checks: int, tmp_path: Path) -> None:
        """run_checks with check_callback=None returns valid tuple without errors.

        Requirement: 76-REQ-6.E2
        """
        checks = [_make_check(f"check_{i}") for i in range(n_checks)]

        with patch("agent_fox.fix.checks.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            # check_callback=None must not raise
            failures, passed = run_checks(checks, tmp_path, check_callback=None)

        assert isinstance(failures, list)
        assert isinstance(passed, list)
        assert len(failures) + len(passed) == n_checks

    @pytest.mark.asyncio
    async def test_run_fix_loop_none_callback_backward_compatible(self, tmp_path: Path) -> None:
        """run_fix_loop with no callbacks returns valid FixResult without errors.

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
            # No progress_callback or check_callback — backward compatible default
            result = await run_fix_loop(tmp_path, config, max_passes=1)

        assert result.termination_reason == TerminationReason.ALL_FIXED
        assert result.passes_completed >= 1


# ---------------------------------------------------------------------------
# TS-76-P5: Progress Event Completeness
# ---------------------------------------------------------------------------


class TestProgressEventCompleteness:
    """TS-76-P5: For any fix loop execution with a callback, every pass produces
    at least a start event and a terminal event.

    Property 5 from design.md
    Validates: 76-REQ-4.1, 76-REQ-4.2, 76-REQ-4.3
    """

    _TERMINAL_STAGES = frozenset({"all_passed", "checks_done", "clusters_found", "cost_limit"})

    @given(max_passes=st.integers(min_value=1, max_value=4))
    @settings(
        max_examples=8,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_every_pass_has_start_and_terminal_event(self, max_passes: int, tmp_path: Path) -> None:
        """For any max_passes, every pass in the fix loop has a start + terminal event.

        Requirement: 76-REQ-4.1, 76-REQ-4.2, 76-REQ-4.3
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
            result = asyncio.run(
                run_fix_loop(
                    tmp_path,
                    config,
                    max_passes=max_passes,
                    progress_callback=callback,
                )
            )

        events = [c.args[0] for c in callback.call_args_list]

        for p in range(1, result.passes_completed + 1):
            pass_events = [e for e in events if e.pass_number == p]
            assert any(e.stage == "checks_start" for e in pass_events), f"Pass {p} should have a checks_start event"
            assert any(e.stage in self._TERMINAL_STAGES for e in pass_events), f"Pass {p} should have a terminal event"


# ---------------------------------------------------------------------------
# TS-76-P6: Check Event Pairing
# ---------------------------------------------------------------------------


class TestCheckEventPairing:
    """TS-76-P6: For any list of checks, the callback receives exactly one start and
    one done event per check.

    Property 6 from design.md
    Validates: 76-REQ-5.1, 76-REQ-5.2
    """

    @given(n_checks=st.integers(min_value=1, max_value=5))
    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_start_and_done_count_equals_check_count(self, n_checks: int, tmp_path: Path) -> None:
        """start_count == done_count == n_checks for any n_checks in 1..5.

        Requirement: 76-REQ-5.1, 76-REQ-5.2
        """
        checks = [_make_check(f"check_{i}") for i in range(n_checks)]
        callback = MagicMock()

        with patch("agent_fox.fix.checks.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            run_checks(checks, tmp_path, check_callback=callback)

        events = [c.args[0] for c in callback.call_args_list]
        starts = [e for e in events if e.stage == "start"]
        dones = [e for e in events if e.stage == "done"]

        assert len(starts) == n_checks, f"Expected {n_checks} start events, got {len(starts)}"
        assert len(dones) == n_checks, f"Expected {n_checks} done events, got {len(dones)}"

    def test_check_event_pairing_includes_timeout(self, tmp_path: Path) -> None:
        """A timed-out check still gets a done event with passed=False.

        Requirement: 76-REQ-5.2
        """
        import subprocess

        checks = [_make_check("slow_check")]
        callback = MagicMock()

        with patch("agent_fox.fix.checks.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["slow_check"], timeout=300)
            run_checks(checks, tmp_path, check_callback=callback)

        events = [c.args[0] for c in callback.call_args_list]
        starts = [e for e in events if e.stage == "start"]
        dones = [e for e in events if e.stage == "done"]

        assert len(starts) == 1, "Timed-out check should still have a start event"
        assert len(dones) == 1, "Timed-out check should still have a done event"
        assert dones[0].passed is False, "Timed-out check done event should have passed=False"
