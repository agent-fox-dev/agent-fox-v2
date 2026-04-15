"""Tests for CLI command renames: lint-spec -> lint-specs.

Test Spec: TS-59-3 through TS-59-6
Requirements: 59-REQ-1.3, 59-REQ-1.4, 59-REQ-1.E2
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from agent_fox.cli.app import main


@pytest.fixture()
def cli_runner() -> CliRunner:
    return CliRunner()


class TestLintSpecsReplacedLintSpec:
    """TS-59-3: `agent-fox lint-specs` produces identical output to
    the former `lint-spec`.

    Requirement: 59-REQ-1.3
    """

    def test_lint_specs_command_accepted(self, cli_runner: CliRunner) -> None:
        """lint-specs command is recognized and runs."""
        with patch("agent_fox.cli.lint_specs.run_lint_specs") as mock_lint:
            from agent_fox.spec.lint import LintResult

            mock_lint.return_value = LintResult(findings=[], fix_results=[], exit_code=0)
            result = cli_runner.invoke(main, ["lint-specs"])

        assert result.exit_code in (0, 1), f"Expected exit code 0 or 1, got {result.exit_code}. Output: {result.output}"


class TestLintSpecsAcceptsFlags:
    """TS-59-4: `lint-specs --all` is accepted without error.

    Requirement: 59-REQ-1.4
    """

    def test_lint_specs_all_flag_accepted(self, cli_runner: CliRunner) -> None:
        """lint-specs --all does not produce 'no such option' error."""
        with patch("agent_fox.cli.lint_specs.run_lint_specs") as mock_lint:
            from agent_fox.spec.lint import LintResult

            mock_lint.return_value = LintResult(findings=[], fix_results=[], exit_code=0)
            result = cli_runner.invoke(main, ["lint-specs", "--all"])

        assert "no such option" not in (result.output or "").lower(), f"Unexpected error: {result.output}"


class TestOldLintSpecRemoved:
    """TS-59-6: `agent-fox lint-spec` exits with error.

    Requirement: 59-REQ-1.E2
    """

    def test_lint_spec_command_rejected(self, cli_runner: CliRunner) -> None:
        """lint-spec command is no longer recognized."""
        result = cli_runner.invoke(main, ["lint-spec"])
        assert result.exit_code != 0, f"Expected non-zero exit code, got {result.exit_code}"
