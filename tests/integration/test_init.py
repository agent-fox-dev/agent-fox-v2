"""Init command integration tests.

Test Spec: TS-01-6 (creates structure), TS-01-7 (idempotent),
           TS-01-8 (gitignore), TS-01-E4 (no git)
Requirements: 01-REQ-3.1, 01-REQ-3.2, 01-REQ-3.3, 01-REQ-3.4, 01-REQ-3.5
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from click.testing import CliRunner

from agent_fox.cli.app import main


class TestInitCreatesStructure:
    """TS-01-6: Init creates project structure."""

    def test_init_creates_agent_fox_directory(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """init creates the .agent-fox/ directory."""
        result = cli_runner.invoke(main, ["init"])

        assert result.exit_code == 0
        assert (tmp_git_repo / ".agent-fox").is_dir()

    def test_init_creates_config_toml(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """init creates .agent-fox/config.toml."""
        cli_runner.invoke(main, ["init"])

        config_path = tmp_git_repo / ".agent-fox" / "config.toml"
        assert config_path.exists()
        # Should be valid TOML (at minimum, not empty)
        content = config_path.read_text()
        assert isinstance(content, str)

    def test_init_creates_hooks_directory(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """init creates .agent-fox/hooks/ directory."""
        cli_runner.invoke(main, ["init"])

        assert (tmp_git_repo / ".agent-fox" / "hooks").is_dir()

    def test_init_creates_worktrees_directory(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """init creates .agent-fox/worktrees/ directory."""
        cli_runner.invoke(main, ["init"])

        assert (tmp_git_repo / ".agent-fox" / "worktrees").is_dir()

    def test_init_creates_develop_branch(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """init creates the develop branch."""
        cli_runner.invoke(main, ["init"])

        result = subprocess.run(
            ["git", "branch", "--list", "develop"],
            cwd=tmp_git_repo,
            capture_output=True,
            text=True,
        )
        assert "develop" in result.stdout

    def test_init_exits_zero(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init exits with code 0 on success."""
        result = cli_runner.invoke(main, ["init"])

        assert result.exit_code == 0


class TestInitIdempotent:
    """TS-01-7: Init is idempotent."""

    def test_second_init_preserves_config(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """Running init twice doesn't overwrite existing config."""
        # First init
        cli_runner.invoke(main, ["init"])

        # Modify config
        config_path = tmp_git_repo / ".agent-fox" / "config.toml"
        config_path.write_text("[orchestrator]\nparallel = 8\n")

        # Second init
        result = cli_runner.invoke(main, ["init"])

        assert result.exit_code == 0
        # Config should be unchanged
        content = config_path.read_text()
        assert "parallel = 8" in content

    def test_second_init_reports_already_initialized(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """Second init reports that project is already initialized."""
        cli_runner.invoke(main, ["init"])

        result = cli_runner.invoke(main, ["init"])

        assert result.exit_code == 0
        assert "already initialized" in result.output.lower()


class TestInitGitignore:
    """TS-01-8: Init updates gitignore."""

    def test_gitignore_contains_agent_fox_glob(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """init adds .agent-fox/* to .gitignore."""
        cli_runner.invoke(main, ["init"])

        gitignore = (tmp_git_repo / ".gitignore").read_text()
        assert ".agent-fox/*" in gitignore

    def test_gitignore_excludes_config(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """init adds !.agent-fox/config.toml exception to .gitignore."""
        cli_runner.invoke(main, ["init"])

        gitignore = (tmp_git_repo / ".gitignore").read_text()
        assert "!.agent-fox/config.toml" in gitignore

    def test_gitignore_excludes_state(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """init adds !.agent-fox/state.jsonl exception to .gitignore."""
        cli_runner.invoke(main, ["init"])

        gitignore = (tmp_git_repo / ".gitignore").read_text()
        assert "!.agent-fox/state.jsonl" in gitignore

    def test_gitignore_excludes_memory(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """init adds !.agent-fox/memory.jsonl exception to .gitignore."""
        cli_runner.invoke(main, ["init"])

        gitignore = (tmp_git_repo / ".gitignore").read_text()
        assert "!.agent-fox/memory.jsonl" in gitignore


class TestInitClaudeSettings:
    """Integration tests for Claude settings creation (Spec 17).

    Requirements: 17-REQ-1.1, 17-REQ-1.2
    """

    def test_init_creates_claude_settings(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """init creates .claude/settings.local.json with canonical permissions."""
        import json

        from agent_fox.cli.init import CANONICAL_PERMISSIONS

        result = cli_runner.invoke(main, ["init"])

        assert result.exit_code == 0
        settings_path = tmp_git_repo / ".claude" / "settings.local.json"
        assert settings_path.exists()

        data = json.loads(settings_path.read_text())
        assert "permissions" in data
        assert "allow" in data["permissions"]
        for perm in CANONICAL_PERMISSIONS:
            assert perm in data["permissions"]["allow"]

    def test_reinit_merges_claude_settings(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """Re-running init merges missing canonical permissions."""
        import json

        from agent_fox.cli.init import CANONICAL_PERMISSIONS

        # First init
        cli_runner.invoke(main, ["init"])

        # Modify settings to have only a subset + custom entry
        settings_path = tmp_git_repo / ".claude" / "settings.local.json"
        custom = {"permissions": {"allow": ["Read", "Bash(custom:*)"]}}
        settings_path.write_text(json.dumps(custom, indent=2) + "\n")

        # Re-init
        result = cli_runner.invoke(main, ["init"])
        assert result.exit_code == 0

        data = json.loads(settings_path.read_text())
        allow = data["permissions"]["allow"]
        # Custom entry preserved
        assert "Bash(custom:*)" in allow
        # All canonical entries present
        for perm in CANONICAL_PERMISSIONS:
            assert perm in allow


class TestInitOutsideGitRepo:
    """TS-01-E4: Init outside git repo fails gracefully."""

    def test_init_outside_git_exits_one(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """Init outside a git repository exits with code 1."""
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["init"])

            assert result.exit_code == 1
        finally:
            os.chdir(original_dir)

    def test_init_outside_git_mentions_git(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """Init outside a git repository mentions 'git' in error."""
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["init"])

            combined = result.output + (result.stderr or "")
            assert "git" in combined.lower()
        finally:
            os.chdir(original_dir)
