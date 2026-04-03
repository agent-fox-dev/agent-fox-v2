"""Integration tests for skill installation via init --skills (Spec 47).

Requirements: 47-REQ-2.1, 47-REQ-2.2, 47-REQ-2.4, 47-REQ-2.5,
              47-REQ-3.1, 47-REQ-3.2, 47-REQ-4.1, 47-REQ-4.2
Test Spec: TS-47-1 through TS-47-7
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import agent_fox
from agent_fox.cli.app import main

# Path to bundled skill templates (for verification)
_SKILLS_DIR = Path(agent_fox.__file__).parent / "_templates" / "skills"


def _bundled_skill_names() -> set[str]:
    """Return the set of bundled skill template names."""
    return {f.name for f in _SKILLS_DIR.iterdir() if f.is_file() and not f.name.startswith(".")}


# ---------------------------------------------------------------------------
# TS-47-1: Skills installed to correct paths
# ---------------------------------------------------------------------------


class TestSkillsInstalledToCorrectPaths:
    """TS-47-1: init --skills creates SKILL.md files at correct paths.

    Requirements: 47-REQ-2.1, 47-REQ-4.1
    """

    def test_skills_installed_to_correct_paths(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Each bundled skill produces .claude/skills/{name}/SKILL.md."""
        result = cli_runner.invoke(main, ["init", "--skills"])

        assert result.exit_code == 0
        for name in _bundled_skill_names():
            skill_path = tmp_git_repo / ".claude" / "skills" / name / "SKILL.md"
            assert skill_path.exists(), f"Missing skill: {name}"


# ---------------------------------------------------------------------------
# TS-47-2: No skills without flag
# ---------------------------------------------------------------------------


class TestNoSkillsWithoutFlag:
    """TS-47-2: init without --skills does not create skill files.

    Requirement: 47-REQ-2.2
    """

    def test_no_skills_without_flag(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """No .claude/skills/ directory created without --skills."""
        result = cli_runner.invoke(main, ["init"])

        assert result.exit_code == 0
        skills_dir = tmp_git_repo / ".claude" / "skills"
        assert not skills_dir.exists() or len(list(skills_dir.iterdir())) == 0


# ---------------------------------------------------------------------------
# TS-47-3: Skills overwrite on re-run
# ---------------------------------------------------------------------------


class TestSkillsOverwriteOnRerun:
    """TS-47-3: Re-running init --skills overwrites existing skill files.

    Requirement: 47-REQ-2.4
    """

    def test_skills_overwrite_on_rerun(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Modified skill file is overwritten with bundled version."""
        # First install
        cli_runner.invoke(main, ["init", "--skills"])

        # Pick the first skill and modify it
        first_name = sorted(_bundled_skill_names())[0]
        skill_path = tmp_git_repo / ".claude" / "skills" / first_name / "SKILL.md"
        skill_path.write_text("modified content")

        # Re-install
        cli_runner.invoke(main, ["init", "--skills"])

        # Should be overwritten with bundled content
        bundled_content = (_SKILLS_DIR / first_name).read_text()
        assert skill_path.read_text() == bundled_content
        assert skill_path.read_text() != "modified content"


# ---------------------------------------------------------------------------
# TS-47-4: Output reports skill count
# ---------------------------------------------------------------------------


class TestOutputReportsSkillCount:
    """TS-47-4: Human-readable output mentions number of skills installed.

    Requirement: 47-REQ-2.5
    """

    def test_output_reports_skill_count(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Output contains 'installed' and the skill count number."""
        result = cli_runner.invoke(main, ["init", "--skills"])

        expected_count = len(_bundled_skill_names())
        assert "installed" in result.output.lower()
        assert str(expected_count) in result.output


# ---------------------------------------------------------------------------
# TS-47-5: JSON output includes skills_installed
# ---------------------------------------------------------------------------


class TestJsonIncludesSkillsInstalled:
    """TS-47-5: JSON output includes skills_installed when --skills provided.

    Requirement: 47-REQ-3.1
    """

    def test_json_includes_skills_installed(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """JSON output has skills_installed integer matching bundled count."""
        result = cli_runner.invoke(main, ["--json", "init", "--skills"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        expected_count = len(_bundled_skill_names())
        assert "skills_installed" in data
        assert data["skills_installed"] == expected_count


# ---------------------------------------------------------------------------
# TS-47-6: JSON output excludes skills_installed without flag
# ---------------------------------------------------------------------------


class TestJsonExcludesSkillsInstalled:
    """TS-47-6: JSON output does not include skills_installed without --skills.

    Requirement: 47-REQ-3.2
    """

    def test_json_excludes_skills_installed(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """JSON output has no skills_installed key without --skills."""
        result = cli_runner.invoke(main, ["--json", "init"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "skills_installed" not in data


# ---------------------------------------------------------------------------
# TS-47-7: Skills work on re-init
# ---------------------------------------------------------------------------


class TestSkillsWorkOnReinit:
    """TS-47-7: --skills works on re-init of already-initialized project.

    Requirement: 47-REQ-4.2
    """

    def test_skills_work_on_reinit(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Re-init with --skills installs skills and reports already initialized."""
        # First init without skills
        cli_runner.invoke(main, ["init"])

        # Re-init with skills
        result = cli_runner.invoke(main, ["init", "--skills"])

        assert result.exit_code == 0
        assert (tmp_git_repo / ".claude" / "skills" / "af-spec" / "SKILL.md").exists()
        assert "already initialized" in result.output.lower()
