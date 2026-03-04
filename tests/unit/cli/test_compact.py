"""Tests for the CLI compact command.

Requirements: 05-REQ-5.1, 05-REQ-5.2, 05-REQ-5.3
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from agent_fox.cli.app import main


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


class TestCompactCommandRegistered:
    """Verify compact command is accessible via CLI."""

    def test_compact_help(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(main, ["compact", "--help"])
        assert result.exit_code == 0
        assert "Compact" in result.output


class TestCompactEmptyStore:
    """Verify compact handles an empty knowledge base."""

    def test_empty_store(self, cli_runner: CliRunner) -> None:
        with patch("agent_fox.cli.compact.compact", return_value=(0, 0)):
            result = cli_runner.invoke(main, ["compact"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower()


class TestCompactWithFacts:
    """Verify compact reports before/after counts."""

    def test_reports_counts(self, cli_runner: CliRunner) -> None:
        with patch("agent_fox.cli.compact.compact", return_value=(10, 7)):
            result = cli_runner.invoke(main, ["compact"])
        assert result.exit_code == 0
        assert "10" in result.output
        assert "7" in result.output
        assert "3" in result.output  # removed count
