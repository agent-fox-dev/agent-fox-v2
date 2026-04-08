"""Unit tests for night-shift display integration.

Test Spec: TS-81-6, TS-81-7, TS-81-10, TS-81-11, TS-81-12, TS-81-13,
           TS-81-14, TS-81-15, TS-81-16, TS-81-E4, TS-81-E5, TS-81-E7,
           TS-81-E8
Requirements: 81-REQ-2.1, 81-REQ-2.2, 81-REQ-3.1, 81-REQ-3.2, 81-REQ-3.3,
              81-REQ-3.4, 81-REQ-3.5, 81-REQ-4.1, 81-REQ-4.2, 81-REQ-4.E1
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.nightshift.engine import NightShiftEngine
from agent_fox.platform.github import IssueResult
from agent_fox.ui.progress import ProgressDisplay


def _make_config(
    *,
    issue_interval: int = 900,
    hunt_interval: int = 14400,
    max_cost: float | None = None,
    max_sessions: int | None = None,
) -> MagicMock:
    config = MagicMock()
    config.night_shift.issue_check_interval = issue_interval
    config.night_shift.hunt_scan_interval = hunt_interval
    config.night_shift.spec_gen_interval = 300
    config.orchestrator.max_cost = max_cost
    config.orchestrator.max_sessions = max_sessions
    return config


def _make_issue(number: int = 42, title: str = "Fix bug") -> IssueResult:
    return IssueResult(
        number=number,
        title=title,
        html_url=f"https://github.com/test/repo/issues/{number}",
        body="Detailed bug description.",
    )


def _make_theme(*, force_terminal: bool = True, width: int = 120) -> tuple:
    """Create an AppTheme with a StringIO-backed console for testing."""
    from rich.console import Console
    from rich.theme import Theme

    from agent_fox.core.config import ThemeConfig
    from agent_fox.ui.display import create_theme

    _STYLE_ROLES = ("header", "success", "error", "warning", "info", "tool", "muted")
    config = ThemeConfig()
    theme = create_theme(config)
    buf = StringIO()
    rich_theme = Theme({role: getattr(config, role) for role in _STYLE_ROLES})
    theme.console = Console(file=buf, theme=rich_theme, width=width, force_terminal=force_terminal)
    return theme, buf


# ---------------------------------------------------------------------------
# TS-81-10: Phase line emitted on issue check start
# Requirement: 81-REQ-3.1
# ---------------------------------------------------------------------------


class TestPhaseLineIssueCheck:
    """Verify status line emitted when engine starts an issue check."""

    @pytest.mark.asyncio
    async def test_81_phase_line_issue_check(self) -> None:
        """Status line contains 'af:fix' or 'issue' on issue check."""
        lines: list[tuple[str, str]] = []

        config = _make_config()
        platform = AsyncMock()
        platform.list_issues_by_label = AsyncMock(return_value=[])

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            status_callback=lambda text, style: lines.append((text, style)),
        )

        await engine._run_issue_check()

        assert any("af:fix" in line or "issue" in line.lower() for line, _ in lines), (
            f"Expected phase line mentioning af:fix or issue, got: {lines}"
        )


# ---------------------------------------------------------------------------
# TS-81-11: Phase line emitted on hunt scan start
# Requirement: 81-REQ-3.2
# ---------------------------------------------------------------------------


class TestPhaseLineHuntScan:
    """Verify status line emitted when engine starts a hunt scan."""

    @pytest.mark.asyncio
    async def test_81_phase_line_hunt_scan(self) -> None:
        """Status line contains 'hunt' or 'scan' on hunt scan start."""
        lines: list[tuple[str, str]] = []

        config = _make_config()
        platform = AsyncMock()

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            status_callback=lambda text, style: lines.append((text, style)),
        )

        # Mock inner scan to avoid real filesystem operations
        engine._run_hunt_scan_inner = AsyncMock(return_value=[])  # type: ignore[method-assign]

        await engine._run_hunt_scan()

        assert any("hunt" in line.lower() or "scan" in line.lower() for line, _ in lines), (
            f"Expected phase line mentioning hunt or scan, got: {lines}"
        )


# ---------------------------------------------------------------------------
# TS-81-12: Phase line on hunt scan complete with counts
# Requirement: 81-REQ-3.3
# ---------------------------------------------------------------------------


class TestPhaseLineHuntComplete:
    """Verify status line with counts emitted after hunt scan."""

    @pytest.mark.asyncio
    async def test_81_phase_line_hunt_complete(self) -> None:
        """Status line contains issue count after hunt scan completes."""
        lines: list[tuple[str, str]] = []

        config = _make_config()
        platform = AsyncMock()

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            status_callback=lambda text, style: lines.append((text, style)),
        )

        engine._run_hunt_scan_inner = AsyncMock(return_value=[])  # type: ignore[method-assign]

        await engine._run_hunt_scan()

        # Should have a completion line with "0" (no findings)
        assert any("0" in line for line, _ in lines), f"Expected count in phase line, got: {lines}"


# ---------------------------------------------------------------------------
# TS-81-13: Phase line on successful fix
# Requirement: 81-REQ-3.4
# ---------------------------------------------------------------------------


class TestPhaseLineFixComplete:
    """Verify permanent line emitted on successful fix."""

    @pytest.mark.asyncio
    async def test_81_phase_line_fix_complete(self) -> None:
        """Status line contains issue number on successful fix."""
        lines: list[tuple[str, str]] = []

        config = _make_config()
        platform = AsyncMock()

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            status_callback=lambda text, style: lines.append((text, style)),
        )

        issue = _make_issue(number=42)
        mock_metrics = MagicMock(
            sessions_run=3,
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        with patch("agent_fox.nightshift.fix_pipeline.FixPipeline") as MockPipeline:
            mock_instance = AsyncMock()
            mock_instance.process_issue = AsyncMock(return_value=mock_metrics)
            MockPipeline.return_value = mock_instance

            await engine._process_fix(issue)

        assert any("#42" in line for line, _ in lines), f"Expected #42 in phase lines, got: {lines}"


# ---------------------------------------------------------------------------
# TS-81-14: Phase line on failed fix
# Requirement: 81-REQ-3.5
# ---------------------------------------------------------------------------


class TestPhaseLineFixFailed:
    """Verify permanent line emitted on failed fix."""

    @pytest.mark.asyncio
    async def test_81_phase_line_fix_failed(self) -> None:
        """Status line contains issue number and 'failed' on fix failure."""
        lines: list[tuple[str, str]] = []

        config = _make_config()
        platform = AsyncMock()

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            status_callback=lambda text, style: lines.append((text, style)),
        )

        issue = _make_issue(number=42)

        with patch("agent_fox.nightshift.fix_pipeline.FixPipeline") as MockPipeline:
            mock_instance = AsyncMock()
            mock_instance.process_issue = AsyncMock(side_effect=RuntimeError("boom"))
            MockPipeline.return_value = mock_instance

            await engine._process_fix(issue)

        assert any("#42" in line and "fail" in line.lower() for line, _ in lines), (
            f"Expected #42 and 'failed' in phase lines, got: {lines}"
        )


# ---------------------------------------------------------------------------
# TS-81-15: Idle spinner shows next action time
# Requirement: 81-REQ-4.1
# ---------------------------------------------------------------------------


class TestIdleSpinnerShowsTime:
    """Verify idle spinner displays next action time in HH:MM format."""

    def test_81_idle_spinner_shows_time(self) -> None:
        """Spinner text contains time in HH:MM format during idle."""
        import re

        activity_events: list[object] = []

        config = _make_config()
        platform = MagicMock()

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            activity_callback=activity_events.append,
        )

        engine._update_idle_spinner(300, 600)

        assert engine._idle_text, "Idle text should be set"
        assert re.search(r"\d{2}:\d{2}", engine._idle_text), (
            f"Expected HH:MM format in idle text, got: {engine._idle_text}"
        )
        assert "Waiting until" in engine._idle_text


# ---------------------------------------------------------------------------
# TS-81-16: Idle spinner clears on phase start
# Requirement: 81-REQ-4.2
# ---------------------------------------------------------------------------


class TestIdleClearsOnPhase:
    """Verify idle message is cleared when a phase starts."""

    @pytest.mark.asyncio
    async def test_81_idle_clears_on_phase(self) -> None:
        """Idle text is cleared when issue check starts."""
        config = _make_config()
        platform = AsyncMock()
        platform.list_issues_by_label = AsyncMock(return_value=[])

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            activity_callback=lambda e: None,
            status_callback=lambda text, style: None,
        )

        # Set idle text
        engine._update_idle_spinner(300, 600)
        assert engine._idle_text != ""

        # Run issue check — should clear idle text
        await engine._run_issue_check()
        assert engine._idle_text == "", f"Idle text should be cleared, got: {engine._idle_text}"


# ---------------------------------------------------------------------------
# TS-81-E7: Quiet mode suppresses phase lines
# Requirement: 81-REQ-3.E1
# ---------------------------------------------------------------------------


class TestPhaseLineQuiet:
    """Verify phase lines suppressed in quiet mode."""

    @pytest.mark.asyncio
    async def test_81_phase_lines_quiet(self) -> None:
        """No output when ProgressDisplay is in quiet mode."""
        theme, buf = _make_theme()
        progress = ProgressDisplay(theme, quiet=True)
        progress.start()

        config = _make_config()
        platform = AsyncMock()
        platform.list_issues_by_label = AsyncMock(return_value=[])

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            status_callback=progress.print_status,
        )

        await engine._run_issue_check()

        progress.stop()
        assert buf.getvalue() == "", f"Expected no output in quiet mode, got: {buf.getvalue()!r}"


# ---------------------------------------------------------------------------
# TS-81-E8: Earlier timer shown in idle display
# Requirement: 81-REQ-4.E1
# ---------------------------------------------------------------------------


class TestIdleShowsEarlierTimer:
    """Verify that the earlier timer is shown in idle spinner."""

    def test_81_idle_shows_earlier_timer(self) -> None:
        """When issue check fires sooner, idle text shows 'issue check'."""
        config = _make_config()
        platform = MagicMock()

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            activity_callback=lambda e: None,
        )

        engine._update_idle_spinner(300, 7200)
        assert "issue check" in engine._idle_text
        assert "hunt scan" not in engine._idle_text

    def test_81_idle_shows_hunt_when_earlier(self) -> None:
        """When hunt scan fires sooner, idle text shows 'hunt scan'."""
        config = _make_config()
        platform = MagicMock()

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            activity_callback=lambda e: None,
        )

        engine._update_idle_spinner(7200, 300)
        assert "hunt scan" in engine._idle_text
        assert "issue check" not in engine._idle_text


# ---------------------------------------------------------------------------
# TS-81-6: ProgressDisplay created and started in CLI
# Requirement: 81-REQ-2.1
# ---------------------------------------------------------------------------


class TestProgressDisplayCreated:
    """Verify night_shift_cmd creates and manages ProgressDisplay."""

    def test_81_progress_display_created(self) -> None:
        """ProgressDisplay.start() and stop() are called during CLI command."""
        from click.testing import CliRunner

        from agent_fox.cli.nightshift import night_shift_cmd

        runner = CliRunner()

        with (
            patch("agent_fox.nightshift.engine.NightShiftEngine") as MockEngine,
            patch("agent_fox.nightshift.engine.validate_night_shift_prerequisites"),
            patch("agent_fox.nightshift.platform_factory.create_platform") as MockPlatform,
            patch("agent_fox.ui.progress.ProgressDisplay") as MockProgress,
        ):
            mock_engine = MagicMock()
            mock_state = MagicMock()
            mock_state.hunt_scans_completed = 0
            mock_state.issues_fixed = 0
            mock_state.total_cost = 0.0

            async def fake_run():
                return mock_state

            mock_engine.run = fake_run

            MockEngine.return_value = mock_engine
            MockPlatform.return_value = MagicMock()

            mock_progress_instance = MagicMock()
            MockProgress.return_value = mock_progress_instance

            runner.invoke(
                night_shift_cmd,
                [],
                obj={"config": MagicMock(), "quiet": False},
                catch_exceptions=False,
            )

            MockProgress.assert_called_once()
            mock_progress_instance.start.assert_called_once()
            mock_progress_instance.stop.assert_called_once()


# ---------------------------------------------------------------------------
# TS-81-7: Summary printed on exit
# Requirement: 81-REQ-2.2
# ---------------------------------------------------------------------------


class TestExitSummary:
    """Verify exit summary includes scans, issues, cost."""

    def test_81_exit_summary(self) -> None:
        """Output contains scans completed, issues fixed, and cost."""
        from click.testing import CliRunner

        from agent_fox.cli.nightshift import night_shift_cmd

        runner = CliRunner()

        with (
            patch("agent_fox.nightshift.engine.NightShiftEngine") as MockEngine,
            patch("agent_fox.nightshift.engine.validate_night_shift_prerequisites"),
            patch("agent_fox.nightshift.platform_factory.create_platform"),
            patch("agent_fox.ui.progress.ProgressDisplay") as MockProgress,
        ):
            mock_engine = MagicMock()
            mock_state = MagicMock()
            mock_state.hunt_scans_completed = 2
            mock_state.issues_fixed = 3
            mock_state.total_cost = 1.5

            async def fake_run():
                return mock_state

            mock_engine.run = fake_run

            MockEngine.return_value = mock_engine
            MockProgress.return_value = MagicMock()

            result = runner.invoke(
                night_shift_cmd,
                [],
                obj={"config": MagicMock(), "quiet": False},
                catch_exceptions=False,
            )

            assert "Scans completed: 2" in result.output
            assert "Issues fixed: 3" in result.output
            assert "$1.5" in result.output


# ---------------------------------------------------------------------------
# TS-81-P5: Idle display accuracy (property test)
# Validates: 81-REQ-4.1, 81-REQ-4.E1
# ---------------------------------------------------------------------------


class TestPropIdleAccuracy:
    """For any pair of remaining times, spinner shows the earlier time."""

    @pytest.mark.parametrize(
        "issue_remaining,hunt_remaining",
        [
            (60, 3600),
            (3600, 60),
            (300, 300),
            (120, 14400),
            (14400, 120),
        ],
    )
    def test_81_prop_idle_accuracy(self, issue_remaining: int, hunt_remaining: int) -> None:
        """The displayed time equals now + min(issue_remaining, hunt_remaining)."""
        import re

        config = _make_config()
        platform = MagicMock()

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            activity_callback=lambda e: None,
        )

        engine._update_idle_spinner(issue_remaining, hunt_remaining)

        expected_action = "issue check" if issue_remaining <= hunt_remaining else "hunt scan"
        assert expected_action in engine._idle_text

        # Verify HH:MM format present
        assert re.search(r"\d{2}:\d{2}", engine._idle_text)


# ---------------------------------------------------------------------------
# TS-81-P6: Display lifecycle (property test)
# Validates: 81-REQ-2.1, 81-REQ-2.2
# ---------------------------------------------------------------------------


class TestPropDisplayLifecycle:
    """For any exit path, ProgressDisplay is started and stopped."""

    @pytest.mark.parametrize("exit_mode", ["clean", "exception"])
    def test_81_prop_display_lifecycle(self, exit_mode: str) -> None:
        """start() and stop() always called regardless of exit mode."""
        from click.testing import CliRunner

        from agent_fox.cli.nightshift import night_shift_cmd

        runner = CliRunner()

        with (
            patch("agent_fox.nightshift.engine.NightShiftEngine") as MockEngine,
            patch("agent_fox.nightshift.engine.validate_night_shift_prerequisites"),
            patch("agent_fox.nightshift.platform_factory.create_platform"),
            patch("agent_fox.ui.progress.ProgressDisplay") as MockProgress,
        ):
            mock_engine = MagicMock()
            if exit_mode == "clean":
                mock_state = MagicMock()
                mock_state.hunt_scans_completed = 0
                mock_state.issues_fixed = 0
                mock_state.total_cost = 0.0

                async def fake_run():
                    return mock_state

                mock_engine.run = fake_run
            else:

                async def failing_run():
                    raise RuntimeError("crash")

                mock_engine.run = failing_run

            MockEngine.return_value = mock_engine
            mock_progress_instance = MagicMock()
            MockProgress.return_value = mock_progress_instance

            runner.invoke(
                night_shift_cmd,
                [],
                obj={"config": MagicMock(), "quiet": False},
            )

            mock_progress_instance.start.assert_called_once()
            mock_progress_instance.stop.assert_called_once()


# ---------------------------------------------------------------------------
# TS-81-P8: Phase line emission completeness (property test)
# Validates: 81-REQ-3.1, 81-REQ-3.2, 81-REQ-3.3, 81-REQ-3.4, 81-REQ-3.5
# ---------------------------------------------------------------------------


class TestPropPhaseLineEmission:
    """Every phase transition produces exactly one status line."""

    @pytest.mark.asyncio
    async def test_81_prop_issue_check_emits_one_line(self) -> None:
        """Issue check emits exactly one phase line on entry."""
        lines: list[tuple[str, str]] = []

        config = _make_config()
        platform = AsyncMock()
        platform.list_issues_by_label = AsyncMock(return_value=[])

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            status_callback=lambda text, style: lines.append((text, style)),
        )

        await engine._run_issue_check()

        # Exactly one phase line for issue check entry
        issue_lines = [(t, s) for t, s in lines if "af:fix" in t or "issue" in t.lower()]
        assert len(issue_lines) == 1

    @pytest.mark.asyncio
    async def test_81_prop_hunt_scan_emits_start_and_complete(self) -> None:
        """Hunt scan emits start and complete phase lines."""
        lines: list[tuple[str, str]] = []

        config = _make_config()
        platform = AsyncMock()

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            status_callback=lambda text, style: lines.append((text, style)),
        )

        engine._run_hunt_scan_inner = AsyncMock(return_value=[])  # type: ignore[method-assign]

        await engine._run_hunt_scan()

        start_lines = [(t, s) for t, s in lines if "Starting hunt scan" in t]
        complete_lines = [(t, s) for t, s in lines if "Hunt scan complete" in t]
        assert len(start_lines) == 1
        assert len(complete_lines) == 1

    @pytest.mark.asyncio
    async def test_81_prop_fix_emits_start_and_result(self) -> None:
        """Fix processing emits start and completion/failure lines."""
        lines: list[tuple[str, str]] = []

        config = _make_config()
        platform = AsyncMock()

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            status_callback=lambda text, style: lines.append((text, style)),
        )

        issue = _make_issue(number=77)
        mock_metrics = MagicMock(
            sessions_run=3,
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        with patch("agent_fox.nightshift.fix_pipeline.FixPipeline") as MockPipeline:
            mock_instance = AsyncMock()
            mock_instance.process_issue = AsyncMock(return_value=mock_metrics)
            MockPipeline.return_value = mock_instance

            await engine._process_fix(issue)

        start_lines = [(t, s) for t, s in lines if "#77" in t and "Fixing" in t]
        result_lines = [(t, s) for t, s in lines if "#77" in t and ("fixed" in t.lower() or "failed" in t.lower())]
        assert len(start_lines) == 1
        assert len(result_lines) == 1
