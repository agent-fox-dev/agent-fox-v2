"""Integration tests for spec generator lifecycle.

Test Spec: TS-86-20, TS-86-27, TS-86-28
Requirements: 86-REQ-6.*, 86-REQ-8.*
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from anthropic.types import TextBlock

from agent_fox.nightshift.config import NightShiftConfig
from agent_fox.nightshift.spec_gen import (
    SpecGenerator,
    SpecPackage,
)
from agent_fox.platform.github import IssueResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides: object) -> NightShiftConfig:
    """Create NightShiftConfig with overrides."""
    defaults: dict[str, object] = {
        "max_clarification_rounds": 3,
        "max_budget_usd": 2.0,
        "spec_gen_model_tier": "ADVANCED",
    }
    defaults.update(overrides)
    return NightShiftConfig.model_validate(defaults)


def _make_platform() -> MagicMock:
    """Create a mock platform."""
    platform = MagicMock()
    platform.list_issues_by_label = AsyncMock(return_value=[])
    platform.assign_label = AsyncMock()
    platform.remove_label = AsyncMock()
    platform.add_issue_comment = AsyncMock()
    platform.close_issue = AsyncMock()
    platform.get_issue = AsyncMock()
    platform.list_issue_comments = AsyncMock(return_value=[])
    platform.create_pull_request = AsyncMock()
    return platform


def _make_issue(
    number: int = 42,
    title: str = "Add widget support",
    body: str = "We need widget support.",
    html_url: str | None = None,
) -> IssueResult:
    if html_url is None:
        html_url = f"https://github.com/org/repo/issues/{number}"
    return IssueResult(number=number, title=title, html_url=html_url, body=body)


def _mock_ai_response(text: str = "Generated content") -> MagicMock:
    """Create a mock AI response."""
    resp = MagicMock()
    resp.content = [TextBlock(type="text", text=text)]
    resp.usage.input_tokens = 100
    resp.usage.output_tokens = 50
    resp.usage.cache_read_input_tokens = 0
    resp.usage.cache_creation_input_tokens = 0
    return resp


# ---------------------------------------------------------------------------
# TS-86-20: generate 5-file spec package
# Requirements: 86-REQ-6.1
# ---------------------------------------------------------------------------


class TestGenerateSpecPackage:
    """Verify _generate_spec_package produces all 5 files."""

    async def test_produces_five_files(self) -> None:
        """TS-86-20: SpecPackage with 5 files."""
        platform = _make_platform()
        gen = SpecGenerator(
            platform=platform,
            config=_make_config(),
            repo_root=Path("/tmp/test-repo"),
        )

        issue = _make_issue(number=42)

        mock_ai = AsyncMock(return_value=_mock_ai_response("Generated document"))

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            package = await gen._generate_spec_package(issue, [], MagicMock())

        expected_files = {"prd.md", "requirements.md", "design.md", "test_spec.md", "tasks.md"}
        assert set(package.files.keys()) == expected_files
        assert all(len(content) > 0 for content in package.files.values())


# ---------------------------------------------------------------------------
# TS-86-27: landing creates feature branch and commits
# Requirements: 86-REQ-8.1
# ---------------------------------------------------------------------------


class TestLandSpec:
    """Verify _land_spec creates a branch, writes files, and commits."""

    async def test_creates_branch_and_commits(self, tmp_path: Path) -> None:
        """TS-86-27: Branch created, files written, commit made."""
        import subprocess

        # Set up a real git repo
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        # Create initial commit on develop
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "checkout", "-b", "develop"],
            check=True,
            capture_output=True,
        )
        (tmp_path / ".specs").mkdir()

        platform = _make_platform()
        config = _make_config()
        config.merge_strategy = "direct"
        gen = SpecGenerator(platform=platform, config=config, repo_root=tmp_path)

        package = SpecPackage(
            spec_name="87_test_spec",
            files={
                "prd.md": "# PRD\nContent",
                "requirements.md": "# Requirements",
                "design.md": "# Design",
                "test_spec.md": "# Tests",
                "tasks.md": "# Tasks",
            },
            source_issue_url="https://github.com/org/repo/issues/42",
        )

        commit_hash = await gen._land_spec(package, 42)

        assert len(commit_hash) > 0
        assert (tmp_path / ".specs" / "87_test_spec" / "prd.md").exists()

        # Verify commit message
        log = subprocess.run(
            ["git", "-C", str(tmp_path), "log", "--oneline", "-1"],
            capture_output=True,
            text=True,
        )
        assert "feat(spec): generate 87_test_spec from #42" in log.stdout


# ---------------------------------------------------------------------------
# TS-86-28: direct merge strategy
# Requirements: 86-REQ-8.2
# ---------------------------------------------------------------------------


class TestDirectMergeStrategy:
    """Verify direct merge strategy merges and deletes branch."""

    async def test_merges_and_deletes_branch(self, tmp_path: Path) -> None:
        """TS-86-28: Branch merged into develop. Feature branch deleted."""
        import subprocess

        # Set up a real git repo
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "checkout", "-b", "develop"],
            check=True,
            capture_output=True,
        )
        (tmp_path / ".specs").mkdir()

        platform = _make_platform()
        config = _make_config()
        config.merge_strategy = "direct"
        gen = SpecGenerator(platform=platform, config=config, repo_root=tmp_path)

        package = SpecPackage(
            spec_name="87_test_spec",
            files={
                "prd.md": "# PRD",
                "requirements.md": "# Req",
                "design.md": "# Design",
                "test_spec.md": "# Tests",
                "tasks.md": "# Tasks",
            },
            source_issue_url="https://github.com/org/repo/issues/42",
        )

        await gen._land_spec(package, 42)

        # Verify on develop branch
        branch = subprocess.run(
            ["git", "-C", str(tmp_path), "branch", "--show-current"],
            capture_output=True,
            text=True,
        )
        assert "develop" in branch.stdout

        # Verify feature branch deleted
        branches = subprocess.run(
            ["git", "-C", str(tmp_path), "branch"],
            capture_output=True,
            text=True,
        )
        assert "spec/87_test_spec" not in branches.stdout
