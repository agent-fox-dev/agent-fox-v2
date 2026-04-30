"""Tests for nightshift CLI wiring to DaemonRunner.

Verifies that cli/nightshift.py uses DaemonRunner instead of
NightShiftEngine.run() for lifecycle management, and that CLI flags
are properly passed through to build_streams().
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from agent_fox.cli.nightshift import night_shift_cmd


def _make_config() -> MagicMock:
    """Create a mock config matching expected structure."""
    config = MagicMock()
    config.max_budget_usd = 10.0
    ns = MagicMock()
    ns.enabled_streams = ["specs", "fixes", "hunts"]
    ns.spec_interval = 60
    ns.issue_check_interval = 900
    ns.hunt_scan_interval = 14400
    config.night_shift = ns
    config.platform.type = "github"
    config.theme = None
    config.orchestrator.max_cost = 10.0
    return config


# Patch targets are at their definition sites since they're imported
# inside the function body.
_PATCHES = {
    "validate": "agent_fox.nightshift.engine.validate_night_shift_prerequisites",
    "create_platform": "agent_fox.nightshift.platform_factory.create_platform",
    "progress_cls": "agent_fox.ui.progress.ProgressDisplay",
    "create_theme": "agent_fox.ui.display.create_theme",
    "daemon_runner": "agent_fox.nightshift.daemon.DaemonRunner",
    "build_streams": "agent_fox.nightshift.streams.build_streams",
    "engine_cls": "agent_fox.nightshift.engine.NightShiftEngine",
    "shared_budget": "agent_fox.nightshift.daemon.SharedBudget",
}


class TestCliUsesDaemonRunner:
    """Verify CLI wires through DaemonRunner, not NightShiftEngine.run()."""

    def test_cli_creates_daemon_runner(self) -> None:
        """The CLI creates a DaemonRunner and calls runner.run()."""
        from agent_fox.nightshift.daemon import DaemonState

        mock_state = DaemonState(total_cost=0.5, issues_fixed=1)

        with (
            patch(_PATCHES["validate"]),
            patch(_PATCHES["create_platform"], return_value=MagicMock()),
            patch(_PATCHES["progress_cls"]) as mock_progress_cls,
            patch(_PATCHES["create_theme"]),
            patch(_PATCHES["daemon_runner"]) as mock_runner_cls,
            patch(_PATCHES["build_streams"], return_value=[MagicMock()]),
            patch(_PATCHES["engine_cls"]) as mock_engine_cls,
            patch(_PATCHES["shared_budget"]),
        ):
            mock_progress = MagicMock()
            mock_progress_cls.return_value = mock_progress

            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_state)
            mock_runner_cls.return_value = mock_runner

            mock_engine = MagicMock()
            mock_engine.state = MagicMock()
            mock_engine.state.issues_fixed = 1
            mock_engine.state.hunt_scans_completed = 0
            mock_engine_cls.return_value = mock_engine

            runner = CliRunner()
            runner.invoke(
                night_shift_cmd,
                [],
                obj={"config": _make_config(), "quiet": False},
                catch_exceptions=False,
            )

            # DaemonRunner was created and run() was called
            mock_runner_cls.assert_called_once()
            mock_runner.run.assert_awaited_once()

    def test_cli_passes_no_flags_to_build_streams(self) -> None:
        """CLI --no-* flags are forwarded to build_streams()."""
        from agent_fox.nightshift.daemon import DaemonState

        mock_state = DaemonState()

        with (
            patch(_PATCHES["validate"]),
            patch(_PATCHES["create_platform"], return_value=MagicMock()),
            patch(_PATCHES["progress_cls"]) as mock_progress_cls,
            patch(_PATCHES["create_theme"]),
            patch(_PATCHES["daemon_runner"]) as mock_runner_cls,
            patch(_PATCHES["build_streams"], return_value=[MagicMock()]) as mock_build,
            patch(_PATCHES["engine_cls"]) as mock_engine_cls,
            patch(_PATCHES["shared_budget"]),
        ):
            mock_progress = MagicMock()
            mock_progress_cls.return_value = mock_progress

            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_state)
            mock_runner_cls.return_value = mock_runner

            mock_engine = MagicMock()
            mock_engine.state = MagicMock()
            mock_engine.state.issues_fixed = 0
            mock_engine.state.hunt_scans_completed = 0
            mock_engine_cls.return_value = mock_engine

            runner = CliRunner()
            runner.invoke(
                night_shift_cmd,
                ["--no-fixes", "--no-hunts"],
                obj={"config": _make_config(), "quiet": False},
                catch_exceptions=False,
            )

            mock_build.assert_called_once()
            call_kwargs = mock_build.call_args
            assert call_kwargs.kwargs["no_fixes"] is True
            assert call_kwargs.kwargs["no_hunts"] is True
            assert call_kwargs.kwargs["no_specs"] is False

    def test_engine_run_not_called(self) -> None:
        """Engine.run() must NOT be called — DaemonRunner manages lifecycle."""
        from agent_fox.nightshift.daemon import DaemonState

        mock_state = DaemonState()

        with (
            patch(_PATCHES["validate"]),
            patch(_PATCHES["create_platform"], return_value=MagicMock()),
            patch(_PATCHES["progress_cls"]) as mock_progress_cls,
            patch(_PATCHES["create_theme"]),
            patch(_PATCHES["daemon_runner"]) as mock_runner_cls,
            patch(_PATCHES["build_streams"], return_value=[MagicMock()]),
            patch(_PATCHES["engine_cls"]) as mock_engine_cls,
            patch(_PATCHES["shared_budget"]),
        ):
            mock_progress = MagicMock()
            mock_progress_cls.return_value = mock_progress

            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_state)
            mock_runner_cls.return_value = mock_runner

            mock_engine = MagicMock()
            mock_engine.state = MagicMock()
            mock_engine.state.issues_fixed = 0
            mock_engine.state.hunt_scans_completed = 0
            mock_engine.run = AsyncMock()
            mock_engine_cls.return_value = mock_engine

            runner = CliRunner()
            runner.invoke(
                night_shift_cmd,
                [],
                obj={"config": _make_config(), "quiet": False},
                catch_exceptions=False,
            )

            # engine.run() should NOT have been called
            mock_engine.run.assert_not_awaited()
            # runner.run() should have been called
            mock_runner.run.assert_awaited_once()


class TestCliSpinnerCallbackWiring:
    """Verify CLI wires spinner_callback=progress.update_spinner_text to NightShiftEngine."""

    def test_spinner_callback_wired_to_engine(self) -> None:
        """CLI passes progress.update_spinner_text as spinner_callback to NightShiftEngine."""
        from agent_fox.nightshift.daemon import DaemonState

        mock_state = DaemonState()

        with (
            patch(_PATCHES["validate"]),
            patch(_PATCHES["create_platform"], return_value=MagicMock()),
            patch(_PATCHES["progress_cls"]) as mock_progress_cls,
            patch(_PATCHES["create_theme"]),
            patch(_PATCHES["daemon_runner"]) as mock_runner_cls,
            patch(_PATCHES["build_streams"], return_value=[MagicMock()]),
            patch(_PATCHES["engine_cls"]) as mock_engine_cls,
            patch(_PATCHES["shared_budget"]),
        ):
            mock_progress = MagicMock()
            mock_progress_cls.return_value = mock_progress

            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_state)
            mock_runner_cls.return_value = mock_runner

            mock_engine = MagicMock()
            mock_engine.state = MagicMock()
            mock_engine.state.issues_fixed = 0
            mock_engine.state.hunt_scans_completed = 0
            mock_engine_cls.return_value = mock_engine

            runner = CliRunner()
            runner.invoke(
                night_shift_cmd,
                [],
                obj={"config": _make_config(), "quiet": False},
                catch_exceptions=False,
            )

            # Verify NightShiftEngine was created with spinner_callback set
            call_kwargs = mock_engine_cls.call_args.kwargs
            assert "spinner_callback" in call_kwargs, (
                "NightShiftEngine should be constructed with spinner_callback"
            )
            assert call_kwargs["spinner_callback"] is mock_progress.update_spinner_text


class TestNightShiftSpecsDirFlag:
    """Verify --specs-dir is wired through to discover_new_specs_gated (issue #498)."""

    def _invoke_and_capture_discover_fn(
        self, extra_args: list[str]
    ) -> tuple[object | None, object]:
        """Invoke night_shift_cmd and return (captured_discover_fn, mock_discover_gated).

        The discover_fn is the closure passed to build_streams; mock_discover_gated
        is the patched discover_new_specs_gated. After this method returns the caller
        can await discover_fn() inside its own asyncio.run() to drive assertions.
        """
        import asyncio
        from unittest.mock import AsyncMock

        from agent_fox.nightshift.daemon import DaemonState

        captured: dict[str, object] = {}
        mock_state = DaemonState(total_cost=0.0, issues_fixed=0)

        def _capture_build_streams(*args: object, **kwargs: object) -> list:
            # build_streams(config, *, discover_fn=..., ...)
            captured["discover_fn"] = kwargs.get("discover_fn")
            return [MagicMock()]

        with (
            patch(_PATCHES["validate"]),
            patch(_PATCHES["create_platform"], return_value=MagicMock()),
            patch(_PATCHES["progress_cls"]) as mock_progress_cls,
            patch(_PATCHES["create_theme"]),
            patch(_PATCHES["daemon_runner"]) as mock_runner_cls,
            patch(_PATCHES["build_streams"], side_effect=_capture_build_streams),
            patch(_PATCHES["engine_cls"]) as mock_engine_cls,
            patch(_PATCHES["shared_budget"]),
            # discover_new_specs_gated is imported inside the function body with
            # `from agent_fox.engine.hot_load import discover_new_specs_gated`
            # so patching at the source module makes the closure see the mock.
            patch(
                "agent_fox.engine.hot_load.discover_new_specs_gated",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_discover,
        ):
            mock_progress = MagicMock()
            mock_progress_cls.return_value = mock_progress

            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_state)
            mock_runner_cls.return_value = mock_runner

            mock_engine = MagicMock()
            mock_engine.state = MagicMock()
            mock_engine.state.issues_fixed = 0
            mock_engine.state.hunt_scans_completed = 0
            mock_engine_cls.return_value = mock_engine

            runner = CliRunner()
            runner.invoke(
                night_shift_cmd,
                extra_args,
                obj={"config": _make_config(), "quiet": False},
                catch_exceptions=False,
            )

            discover_fn = captured.get("discover_fn")
            if discover_fn is not None:
                # Drive the closure so mock_discover records a call.
                asyncio.run(discover_fn())

            # Return a copy of the mock call args before the context exits
            discover_call_args = mock_discover.call_args
            discover_await_count = mock_discover.await_count

        return discover_fn, discover_call_args, discover_await_count  # type: ignore[return-value]

    def test_custom_specs_dir_used_in_discover_fn(self, tmp_path: Path) -> None:
        """AC-3: --specs-dir passes custom path to discover_new_specs_gated."""
        custom_dir = tmp_path / "myspecs"
        custom_dir.mkdir()

        discover_fn, call_args, await_count = self._invoke_and_capture_discover_fn(  # type: ignore[misc]
            ["--specs-dir", str(custom_dir)]
        )
        assert discover_fn is not None, "discover_fn was not captured from build_streams call"
        assert await_count >= 1, "discover_new_specs_gated was never awaited"
        called_specs_dir = call_args.args[0]
        assert called_specs_dir == custom_dir, (
            f"Expected discover_new_specs_gated called with {custom_dir}, got {called_specs_dir}"
        )

    def test_no_specs_dir_uses_resolve_spec_root(self) -> None:
        """AC-4: without --specs-dir, night-shift falls back to resolve_spec_root."""
        default_path = Path("/resolved/default/specs")
        with patch("agent_fox.core.config.resolve_spec_root", return_value=default_path) as mock_resolve:
            self._invoke_and_capture_discover_fn([])
            mock_resolve.assert_called_once()

    def test_specs_dir_help_text_present(self) -> None:
        """AC-5: --specs-dir appears in night-shift --help output."""
        runner = CliRunner()
        result = runner.invoke(night_shift_cmd, ["--help"])
        assert "--specs-dir" in result.output, (
            "--specs-dir option not found in `night-shift --help` output"
        )
        assert "PATH" in result.output, (
            "PATH type annotation not found in `night-shift --help` output for --specs-dir"
        )
