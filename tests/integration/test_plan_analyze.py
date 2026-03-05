"""Integration tests for plan --analyze CLI flag.

Test Spec: TS-20-1 (CLI integration)
Requirements: 20-REQ-1.1
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from agent_fox.cli.app import main


def _setup_project(project_dir: Path) -> None:
    """Create a minimal project structure with multiple specs for analysis."""
    # Create .agent-fox/config.toml
    agent_fox_dir = project_dir / ".agent-fox"
    agent_fox_dir.mkdir(exist_ok=True)
    (agent_fox_dir / "config.toml").write_text("")

    # Create two specs with a cross-spec dependency
    spec1 = project_dir / ".specs" / "01_alpha"
    spec1.mkdir(parents=True)
    (spec1 / "tasks.md").write_text(
        "# Tasks\n\n"
        "- [ ] 1. Write tests\n"
        "  - [ ] 1.1 Unit tests\n"
        "\n"
        "- [ ] 2. Implement\n"
        "  - [ ] 2.1 Core logic\n"
    )

    spec2 = project_dir / ".specs" / "02_beta"
    spec2.mkdir(parents=True)
    (spec2 / "tasks.md").write_text(
        "# Tasks\n\n"
        "- [ ] 1. Write tests\n"
        "  - [ ] 1.1 Unit tests\n"
    )
    (spec2 / "prd.md").write_text(
        "# PRD\n\n"
        "| This Spec | Depends On | What It Uses |\n"
        "|-----------|-----------|---------------|\n"
        "| 02_beta | 01_alpha | Core types |\n"
    )


class TestPlanAnalyzeCLI:
    """Verify plan --analyze produces expected output sections."""

    def test_exits_zero(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """plan --analyze exits with code 0."""
        _setup_project(tmp_git_repo)
        result = cli_runner.invoke(main, ["plan", "--analyze"])
        assert result.exit_code == 0, (
            f"Exit code {result.exit_code}, output:\n{result.output}"
        )

    def test_output_contains_phase(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """plan --analyze output contains 'Phase' heading."""
        _setup_project(tmp_git_repo)
        result = cli_runner.invoke(main, ["plan", "--analyze"])
        assert "Phase" in result.output

    def test_output_contains_critical_path(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """plan --analyze output contains 'Critical Path' section."""
        _setup_project(tmp_git_repo)
        result = cli_runner.invoke(main, ["plan", "--analyze"])
        assert "Critical Path" in result.output

    def test_output_contains_summary(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """plan --analyze output contains summary statistics."""
        _setup_project(tmp_git_repo)
        result = cli_runner.invoke(main, ["plan", "--analyze"])
        assert "Peak workers" in result.output or "peak" in result.output.lower()
