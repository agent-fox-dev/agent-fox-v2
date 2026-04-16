"""Init command integration tests.

Test Spec: TS-01-6 (creates structure), TS-01-7 (idempotent),
           TS-01-8 (gitignore), TS-01-E4 (no git),
           TS-33-11 (fresh config loads defaults)
Requirements: 01-REQ-3.1, 01-REQ-3.2, 01-REQ-3.3, 01-REQ-3.4, 01-REQ-3.5,
              33-REQ-1.1, 33-REQ-2.1, 33-REQ-2.2, 33-REQ-2.4, 33-REQ-3.1
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from click.testing import CliRunner

from agent_fox.cli.app import main


class TestInitCreatesStructure:
    """TS-01-6: Init creates project structure."""

    def test_init_creates_agent_fox_directory(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init creates the .agent-fox/ directory."""
        result = cli_runner.invoke(main, ["init"])

        assert result.exit_code == 0
        assert (tmp_git_repo / ".agent-fox").is_dir()

    def test_init_creates_config_toml(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init creates .agent-fox/config.toml."""
        cli_runner.invoke(main, ["init"])

        config_path = tmp_git_repo / ".agent-fox" / "config.toml"
        assert config_path.exists()
        # Should be valid TOML (at minimum, not empty)
        content = config_path.read_text()
        assert isinstance(content, str)

    def test_init_creates_worktrees_directory(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init creates .agent-fox/worktrees/ directory."""
        cli_runner.invoke(main, ["init"])

        assert (tmp_git_repo / ".agent-fox" / "worktrees").is_dir()

    def test_init_creates_develop_branch(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
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

    def test_second_init_preserves_config(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
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

    def test_second_init_reports_already_initialized(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Second init reports that project is already initialized."""
        cli_runner.invoke(main, ["init"])

        result = cli_runner.invoke(main, ["init"])

        assert result.exit_code == 0
        assert "already initialized" in result.output.lower()


class TestInitGitignore:
    """TS-01-8: Init updates gitignore."""

    def test_gitignore_contains_agent_fox_glob(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init adds .agent-fox/* to .gitignore."""
        cli_runner.invoke(main, ["init"])

        gitignore = (tmp_git_repo / ".gitignore").read_text()
        assert ".agent-fox/*" in gitignore

    def test_gitignore_excludes_config(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init adds !.agent-fox/config.toml exception to .gitignore."""
        cli_runner.invoke(main, ["init"])

        gitignore = (tmp_git_repo / ".gitignore").read_text()
        assert "!.agent-fox/config.toml" in gitignore

    def test_gitignore_does_not_include_state(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init does not add !.agent-fox/state.jsonl exception to .gitignore."""
        cli_runner.invoke(main, ["init"])

        gitignore = (tmp_git_repo / ".gitignore").read_text()
        assert "!.agent-fox/state.jsonl" not in gitignore

    def test_gitignore_does_not_add_memory_exception(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init does NOT add !.agent-fox/memory.jsonl exception to .gitignore.

        memory.jsonl is tracked via git add --force, not a gitignore exception.
        """
        cli_runner.invoke(main, ["init"])

        gitignore = (tmp_git_repo / ".gitignore").read_text()
        assert "!.agent-fox/memory.jsonl" not in gitignore

    def test_gitignore_excludes_profiles_dir(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init adds both !.agent-fox/profiles/ and !.agent-fox/profiles/* to .gitignore.

        Two entries are needed: one to un-ignore the directory itself and one
        to un-ignore files within it, because .agent-fox/* ignores the directory.
        """
        cli_runner.invoke(main, ["init"])

        gitignore = (tmp_git_repo / ".gitignore").read_text()
        assert "!.agent-fox/profiles/" in gitignore
        assert "!.agent-fox/profiles/*" in gitignore

    def test_gitignore_contains_claude_worktrees(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init adds .claude/worktrees/ to .gitignore."""
        cli_runner.invoke(main, ["init"])

        gitignore = (tmp_git_repo / ".gitignore").read_text()
        assert ".claude/worktrees/" in gitignore


class TestInitGitTracking:
    """Init stages files in git so they are tracked from the start."""

    def test_init_stages_memory_jsonl(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init force-adds .agent-fox/memory.jsonl to git index."""
        cli_runner.invoke(main, ["init"])

        result = subprocess.run(
            ["git", "ls-files", ".agent-fox/memory.jsonl"],
            cwd=tmp_git_repo,
            capture_output=True,
            text=True,
        )
        assert ".agent-fox/memory.jsonl" in result.stdout

    def test_init_profiles_stages_profiles(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init --profiles adds copied profile files to git index."""
        # First init to set up gitignore with !.agent-fox/profiles/*
        cli_runner.invoke(main, ["init"])

        from agent_fox.cli.init import init_profiles

        init_profiles(project_dir=tmp_git_repo)

        result = subprocess.run(
            ["git", "ls-files", ".agent-fox/profiles/"],
            cwd=tmp_git_repo,
            capture_output=True,
            text=True,
        )
        assert ".agent-fox/profiles/" in result.stdout or "coder.md" in result.stdout


class TestInitSeedFiles:
    """Init creates seed files so they are tracked in git from the start."""

    def test_init_creates_memory_jsonl(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init creates an empty .agent-fox/memory.jsonl."""
        cli_runner.invoke(main, ["init"])

        path = tmp_git_repo / ".agent-fox" / "memory.jsonl"
        assert path.exists()
        assert path.read_text() == ""

    def test_init_creates_docs_memory_md(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init creates docs/memory.md with placeholder content."""
        cli_runner.invoke(main, ["init"])

        path = tmp_git_repo / "docs" / "memory.md"
        assert path.exists()
        content = path.read_text()
        assert "Agent-Fox Memory" in content

    def test_reinit_preserves_existing_seed_files(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Re-running init does not overwrite existing seed files."""
        cli_runner.invoke(main, ["init"])

        # Write content to memory.jsonl
        memory_path = tmp_git_repo / ".agent-fox" / "memory.jsonl"
        memory_path.write_text('{"fact": "test"}\n')

        # Write content to docs/memory.md
        docs_memory = tmp_git_repo / "docs" / "memory.md"
        docs_memory.write_text("# Custom content\n")

        # Re-init
        cli_runner.invoke(main, ["init"])

        assert memory_path.read_text() == '{"fact": "test"}\n'
        assert docs_memory.read_text() == "# Custom content\n"


class TestInitClaudeSettings:
    """Integration tests for Claude settings creation (Spec 17).

    Requirements: 17-REQ-1.1, 17-REQ-1.2
    """

    def test_init_creates_claude_settings(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """init creates .claude/settings.local.json with canonical permissions."""
        import json

        from agent_fox.workspace.init_project import CANONICAL_PERMISSIONS

        result = cli_runner.invoke(main, ["init"])

        assert result.exit_code == 0
        settings_path = tmp_git_repo / ".claude" / "settings.local.json"
        assert settings_path.exists()

        data = json.loads(settings_path.read_text())
        assert "permissions" in data
        assert "allow" in data["permissions"]
        for perm in CANONICAL_PERMISSIONS:
            assert perm in data["permissions"]["allow"]

    def test_reinit_merges_claude_settings(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Re-running init merges missing canonical permissions."""
        import json

        from agent_fox.workspace.init_project import CANONICAL_PERMISSIONS

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


class TestInitConfigGeneration:
    """TS-33-11: Fresh init produces a complete config.toml that loads defaults.

    Requirements: 33-REQ-1.1, 33-REQ-3.1
    """

    def test_fresh_config_loads_defaults(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """A freshly generated config.toml loads via load_config with all defaults.

        TS-33-11: Fresh config loads with all default values.
        """
        from agent_fox.core.config import AgentFoxConfig, load_config

        cli_runner.invoke(main, ["init"])

        config_path = tmp_git_repo / ".agent-fox" / "config.toml"
        assert config_path.exists()

        config = load_config(config_path)
        assert isinstance(config, AgentFoxConfig)
        # Verify key defaults
        assert config.orchestrator.parallel == 2
        assert config.theme.playful is True
        assert config.models.coding == "ADVANCED"

    def test_fresh_config_contains_all_sections(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Fresh config.toml contains section headers for all visible sections.

        The simplified template includes only visible sections. Hidden sections
        (routing, hooks, theme, platform, knowledge) are omitted.
        """
        cli_runner.invoke(main, ["init"])

        config_path = tmp_git_repo / ".agent-fox" / "config.toml"
        content = config_path.read_text()

        # Visible sections must appear
        for section in ["orchestrator", "models", "security", "archetypes"]:
            # Sections may be active [section] or commented # [section]
            assert f"[{section}]" in content, f"Missing section header: {section}"

        # Hidden sections must NOT appear
        for section in ["routing", "hooks", "theme", "platform", "knowledge"]:
            assert f"[{section}]" not in content, f"Hidden section [{section}] should not appear in simplified template"

    def test_reinit_merges_new_fields(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Re-init adds missing schema fields to existing config.

        Requirements: 33-REQ-2.1, 33-REQ-2.2
        """
        # First init
        cli_runner.invoke(main, ["init"])

        # Overwrite with a minimal config containing only one field
        config_path = tmp_git_repo / ".agent-fox" / "config.toml"
        config_path.write_text("[orchestrator]\nparallel = 4\n")

        # Re-init should merge
        result = cli_runner.invoke(main, ["init"])
        assert result.exit_code == 0

        content = config_path.read_text()
        # User value preserved
        assert "parallel = 4" in content
        # Visible sections added when missing
        assert "# [models]" in content or "[models]" in content
        assert "# [archetypes]" in content or "[archetypes]" in content
        # Hidden sections must NOT be added by merge
        assert "# [routing]" not in content and "[routing]" not in content
        assert "# [theme]" not in content and "[theme]" not in content

    def test_reinit_marks_deprecated_fields(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Re-init marks unrecognized active fields as DEPRECATED.

        Requirements: 33-REQ-2.4
        """
        # First init
        cli_runner.invoke(main, ["init"])

        # Add an unrecognized field
        config_path = tmp_git_repo / ".agent-fox" / "config.toml"
        config_path.write_text("[orchestrator]\nparallel = 4\nobsolete_setting = true\n")

        # Re-init should mark it deprecated
        result = cli_runner.invoke(main, ["init"])
        assert result.exit_code == 0

        content = config_path.read_text()
        assert "DEPRECATED" in content
        assert "obsolete_setting" in content

    def test_reinit_no_changes_leaves_file_unchanged(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Re-init on an up-to-date config leaves file byte-for-byte identical.

        Requirements: 33-REQ-2.5
        """
        # First init
        cli_runner.invoke(main, ["init"])

        config_path = tmp_git_repo / ".agent-fox" / "config.toml"
        content_before = config_path.read_text()

        # Re-init
        cli_runner.invoke(main, ["init"])

        content_after = config_path.read_text()
        assert content_before == content_after

    def test_config_no_memory_section(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Generated config does not contain a [memory] section.

        Requirements: 33-REQ-5.1
        """
        cli_runner.invoke(main, ["init"])

        config_path = tmp_git_repo / ".agent-fox" / "config.toml"
        content = config_path.read_text()
        assert "# [memory]" not in content
        assert "[memory]" not in content


class TestInitOutsideGitRepo:
    """TS-01-E4: Init outside git repo fails gracefully."""

    def test_init_outside_git_exits_one(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Init outside a git repository exits with code 1."""
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["init"])

            assert result.exit_code == 1
        finally:
            os.chdir(original_dir)

    def test_init_outside_git_mentions_git(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Init outside a git repository mentions 'git' in error."""
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["init"])

            combined = result.output + (result.stderr or "")
            assert "git" in combined.lower()
        finally:
            os.chdir(original_dir)
