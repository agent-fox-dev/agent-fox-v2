"""Tests for plan command --specs-dir flag.

Verifies that plan_cmd accepts --specs-dir and passes the supplied path
to build_plan instead of the config-resolved default.

Requirements: AC-1, AC-2 (issue #498)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from agent_fox.cli.plan import plan_cmd
from agent_fox.nightshift.pid import PidStatus


def _make_graph() -> MagicMock:
    """Return a minimal TaskGraph-like mock."""
    graph = MagicMock()
    graph.nodes = {}
    graph.edges = []
    graph.order = []
    meta = MagicMock()
    meta.created_at = "2026-01-01T00:00:00"
    meta.fast_mode = False
    meta.filtered_spec = None
    meta.version = "0.0.1"
    graph.metadata = meta
    return graph


# Patch at usage site — build_plan, format_plan_summary and discover_specs are
# imported at the top of agent_fox.cli.plan, so patching must use that module path.
_PATCHES = {
    "build_plan": "agent_fox.cli.plan.build_plan",
    "format_plan_summary": "agent_fox.cli.plan.format_plan_summary",
    "discover_specs": "agent_fox.cli.plan.discover_specs",
    # These are imported inside the function body so patch at definition site.
    "save_plan": "agent_fox.graph.persistence.save_plan",
    "open_knowledge_store": "agent_fox.knowledge.db.open_knowledge_store",
    "resolve_spec_root": "agent_fox.core.config.resolve_spec_root",
}


@pytest.fixture(autouse=True)
def _no_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent the daemon PID check from blocking plan tests."""
    monkeypatch.setattr(
        "agent_fox.nightshift.pid.check_pid_file",
        lambda _path: (PidStatus.ABSENT, None),
    )


class TestPlanSpecsDirFlag:
    """Verify --specs-dir is wired through to build_plan."""

    def test_custom_specs_dir_passed_to_build_plan(self, tmp_path: Path) -> None:
        """AC-1: --specs-dir passes custom path to build_plan, not the config default."""
        custom_dir = tmp_path / "myspecs"
        custom_dir.mkdir()

        mock_graph = _make_graph()
        mock_kb = MagicMock()
        mock_kb.connection = MagicMock()

        with (
            patch(_PATCHES["build_plan"], return_value=mock_graph) as mock_build,
            patch(_PATCHES["format_plan_summary"], return_value="Plan summary"),
            patch(_PATCHES["discover_specs"], return_value=[]),
            patch(_PATCHES["save_plan"]),
            patch(_PATCHES["open_knowledge_store"], return_value=mock_kb),
            patch(_PATCHES["resolve_spec_root"], return_value=Path("/default/specs")) as mock_resolve,
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                ["--specs-dir", str(custom_dir)],
                obj={"config": MagicMock(), "json": False},
                catch_exceptions=False,
            )

            assert result.exit_code == 0, result.output
            # build_plan should be called with the custom path, not the config default
            mock_build.assert_called_once()
            called_specs_dir = mock_build.call_args.args[0]
            assert called_specs_dir == custom_dir, (
                f"Expected build_plan to be called with {custom_dir}, got {called_specs_dir}"
            )
            # resolve_spec_root should NOT have been called
            mock_resolve.assert_not_called()

    def test_no_specs_dir_falls_back_to_resolve_spec_root(self, tmp_path: Path) -> None:
        """AC-2: without --specs-dir, plan falls back to resolve_spec_root."""
        default_dir = tmp_path / ".agent-fox" / "specs"
        default_dir.mkdir(parents=True)

        mock_graph = _make_graph()
        mock_kb = MagicMock()
        mock_kb.connection = MagicMock()

        with (
            patch(_PATCHES["build_plan"], return_value=mock_graph) as mock_build,
            patch(_PATCHES["format_plan_summary"], return_value="Plan summary"),
            patch(_PATCHES["discover_specs"], return_value=[]),
            patch(_PATCHES["save_plan"]),
            patch(_PATCHES["open_knowledge_store"], return_value=mock_kb),
            patch(_PATCHES["resolve_spec_root"], return_value=default_dir) as mock_resolve,
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                [],
                obj={"config": MagicMock(), "json": False},
                catch_exceptions=False,
            )

            assert result.exit_code == 0, result.output
            # resolve_spec_root should have been called (fallback behaviour)
            mock_resolve.assert_called_once()
            called_specs_dir = mock_build.call_args.args[0]
            assert called_specs_dir == default_dir, (
                f"Expected build_plan to be called with {default_dir}, got {called_specs_dir}"
            )

    def test_specs_dir_help_text_present(self) -> None:
        """AC-5: --specs-dir appears in plan --help output."""
        runner = CliRunner()
        result = runner.invoke(plan_cmd, ["--help"])
        assert "--specs-dir" in result.output, (
            "--specs-dir option not found in `plan --help` output"
        )
        assert "PATH" in result.output, (
            "PATH type annotation not found in `plan --help` output for --specs-dir"
        )
