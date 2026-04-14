"""Tests for agent_fox.cli.onboard — Spec 101.

Tests: TS-101-1, TS-101-2, TS-101-14, TS-101-E1
Requirements: 101-REQ-1.1, 101-REQ-1.2, 101-REQ-1.5, 101-REQ-1.E1
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_fox.knowledge.onboard import OnboardResult
from click.testing import CliRunner

from agent_fox.cli.app import main
from agent_fox.core.config import AgentFoxConfig


@pytest.fixture()
def runner() -> CliRunner:
    """Return a Click test runner."""
    return CliRunner()


class TestCommandRegistration:
    """TS-101-1: 'onboard' command is registered in the main CLI group.

    Requirement: 101-REQ-1.1
    """

    def test_onboard_registered_in_cli(self) -> None:
        """Verify 'onboard' appears in the CLI command registry."""
        command_names = list(main.commands.keys())
        assert "onboard" in command_names


class TestDefaultPath:
    """TS-101-2: Onboard uses cwd when --path is not specified.

    Requirement: 101-REQ-1.2
    """

    def test_uses_cwd_when_no_path_given(self, runner: CliRunner) -> None:
        """Verify run_onboard is called with Path.cwd() when --path omitted."""
        with patch(
            "agent_fox.cli.onboard.load_config",
            return_value=AgentFoxConfig(),
        ), patch(
            "agent_fox.cli.onboard.open_knowledge_store",
        ) as mock_open_store, patch(
            "agent_fox.cli.onboard.run_onboard",
            new_callable=AsyncMock,
            return_value=OnboardResult(),
        ) as mock_run:
            mock_store = MagicMock()
            mock_open_store.return_value.__enter__ = MagicMock(return_value=mock_store)
            mock_open_store.return_value.__exit__ = MagicMock(return_value=None)

            result = runner.invoke(main, ["onboard"])

        assert result.exit_code == 0, result.output
        assert mock_run.called
        call_args = mock_run.call_args
        # project_root (first positional arg) should be the cwd
        project_root = call_args.args[0] if call_args.args else call_args.kwargs.get("project_root")
        assert project_root == Path.cwd()

    def test_uses_specified_path_when_given(self, runner: CliRunner, tmp_path: Path) -> None:
        """Verify run_onboard is called with the --path argument when provided."""
        with patch(
            "agent_fox.cli.onboard.load_config",
            return_value=AgentFoxConfig(),
        ), patch(
            "agent_fox.cli.onboard.open_knowledge_store",
        ) as mock_open_store, patch(
            "agent_fox.cli.onboard.run_onboard",
            new_callable=AsyncMock,
            return_value=OnboardResult(),
        ) as mock_run:
            mock_store = MagicMock()
            mock_open_store.return_value.__enter__ = MagicMock(return_value=mock_store)
            mock_open_store.return_value.__exit__ = MagicMock(return_value=None)

            result = runner.invoke(main, ["onboard", "--path", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert mock_run.called
        call_args = mock_run.call_args
        project_root = call_args.args[0] if call_args.args else call_args.kwargs.get("project_root")
        assert project_root == tmp_path


class TestJSONOutput:
    """TS-101-14: JSON output mode emits OnboardResult as JSON to stdout.

    Requirement: 101-REQ-1.5
    """

    def test_json_flag_emits_json_to_stdout(self, runner: CliRunner) -> None:
        """Verify --json produces valid JSON with OnboardResult fields."""
        known_result = OnboardResult(entities_upserted=5, code_facts_created=3)

        with patch(
            "agent_fox.cli.onboard.load_config",
            return_value=AgentFoxConfig(),
        ), patch(
            "agent_fox.cli.onboard.open_knowledge_store",
        ) as mock_open_store, patch(
            "agent_fox.cli.onboard.run_onboard",
            new_callable=AsyncMock,
            return_value=known_result,
        ):
            mock_store = MagicMock()
            mock_open_store.return_value.__enter__ = MagicMock(return_value=mock_store)
            mock_open_store.return_value.__exit__ = MagicMock(return_value=None)

            result = runner.invoke(main, ["--json", "onboard"])

        assert result.exit_code == 0, result.output
        # stdout should contain valid JSON
        parsed = json.loads(result.output)
        assert isinstance(parsed, dict)
        assert parsed["entities_upserted"] == 5
        assert parsed["code_facts_created"] == 3


class TestInvalidPath:
    """TS-101-E1: Error on non-existent path.

    Requirement: 101-REQ-1.E1
    """

    def test_nonexistent_path_fails(self, runner: CliRunner) -> None:
        """Verify non-existent --path returns non-zero exit code."""
        result = runner.invoke(main, ["onboard", "--path", "/nonexistent/path/xyz"])
        assert result.exit_code != 0

    def test_file_path_fails(self, runner: CliRunner, tmp_path: Path) -> None:
        """Verify a file (not directory) passed as --path fails."""
        some_file = tmp_path / "notadir.txt"
        some_file.write_text("I am a file, not a directory")
        result = runner.invoke(main, ["onboard", "--path", str(some_file)])
        assert result.exit_code != 0
