"""Unit tests for issue_summary module.

Test Spec: TS-108-1 through TS-108-17, TS-108-E1, TS-108-E2
Requirements: 108-REQ-1 through 108-REQ-6
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# TS-108-1, TS-108-2, TS-108-3, TS-108-4, TS-108-5
# Requirements: 108-REQ-1.1, 108-REQ-1.2, 108-REQ-1.3, 108-REQ-1.E1,
#               108-REQ-1.E2, 108-REQ-1.E3
# ---------------------------------------------------------------------------


class TestParseSourceUrl:
    """Tests for parse_source_url() function."""

    def test_github_url_returns_source_issue(self, tmp_path: Path) -> None:
        """TS-108-1: parse_source_url returns SourceIssue for GitHub URL.

        Requirements: 108-REQ-1.1, 108-REQ-1.2
        """
        from agent_fox.engine.issue_summary import SourceIssue, parse_source_url

        prd_path = tmp_path / "prd.md"
        prd_path.write_text("# PRD\n\n## Source\n\nSource: https://github.com/agent-fox-dev/agent-fox/issues/359\n")

        result = parse_source_url(prd_path)

        assert result is not None
        assert isinstance(result, SourceIssue)
        assert result.forge == "github"
        assert result.owner == "agent-fox-dev"
        assert result.repo == "agent-fox"
        assert result.issue_number == 359

    def test_missing_prd_returns_none(self, tmp_path: Path) -> None:
        """TS-108-2: parse_source_url returns None for missing prd.md.

        Requirements: 108-REQ-1.E3
        """
        from agent_fox.engine.issue_summary import parse_source_url

        prd_path = tmp_path / "prd.md"  # does not exist
        assert not prd_path.exists()

        result = parse_source_url(prd_path)

        assert result is None

    def test_no_source_section_returns_none(self, tmp_path: Path) -> None:
        """TS-108-3: parse_source_url returns None for missing Source section.

        Requirements: 108-REQ-1.E1
        """
        from agent_fox.engine.issue_summary import parse_source_url

        prd_path = tmp_path / "prd.md"
        prd_path.write_text("# PRD\n\nNo source section here.\n\n## Overview\n\nSome text.\n")

        result = parse_source_url(prd_path)

        assert result is None

    def test_non_url_source_returns_none(self, tmp_path: Path) -> None:
        """TS-108-4: parse_source_url returns None for non-URL source.

        Requirements: 108-REQ-1.E2
        """
        from agent_fox.engine.issue_summary import parse_source_url

        prd_path = tmp_path / "prd.md"
        prd_path.write_text("## Source\n\nSource: Input provided by user via interactive prompt\n")

        result = parse_source_url(prd_path)

        assert result is None

    def test_pure_function_no_exceptions(self, tmp_path: Path) -> None:
        """TS-108-5: parse_source_url is a pure function (no exceptions).

        Requirements: 108-REQ-1.3
        Each variant returns either SourceIssue or None; nothing raises.
        """
        from agent_fox.engine.issue_summary import SourceIssue, parse_source_url

        # Variant 1: missing file
        missing = tmp_path / "nonexistent.md"

        # Variant 2: empty file
        empty = tmp_path / "empty.md"
        empty.write_text("")

        # Variant 3: Source with file path (not a URL)
        file_src = tmp_path / "file_path_src.md"
        file_src.write_text("## Source\n\nSource: /some/file/path.txt\n")

        # Variant 4: Source with GitHub URL
        github_src = tmp_path / "github_src.md"
        github_src.write_text("## Source\n\nSource: https://github.com/org/repo/issues/1\n")

        # Variant 5: Source with unknown URL format
        unknown_src = tmp_path / "unknown_src.md"
        unknown_src.write_text("## Source\n\nSource: https://linear.app/team/issue/123\n")

        variants = [missing, empty, file_src, github_src, unknown_src]

        for path in variants:
            result = parse_source_url(path)
            # Must be None or a valid SourceIssue, never an exception
            assert result is None or isinstance(result, SourceIssue), (
                f"Expected None or SourceIssue for {path.name}, got {type(result)}"
            )


# ---------------------------------------------------------------------------
# TS-108-E1, TS-108-E2
# Requirements: 108-REQ-1.E1, 108-REQ-1.1
# ---------------------------------------------------------------------------


class TestParseSourceUrlEdgeCases:
    """Edge case tests for parse_source_url()."""

    def test_source_section_without_source_line_returns_none(self, tmp_path: Path) -> None:
        """TS-108-E1: ## Source heading present but no Source: line.

        Requirements: 108-REQ-1.E1
        """
        from agent_fox.engine.issue_summary import parse_source_url

        prd_path = tmp_path / "prd.md"
        prd_path.write_text("# PRD\n\n## Source\n\nThis section has text but no 'Source:' prefix line.\n")

        result = parse_source_url(prd_path)

        assert result is None

    def test_multiple_source_sections_uses_first(self, tmp_path: Path) -> None:
        """TS-108-E2: Multiple ## Source sections — uses first one.

        Requirements: 108-REQ-1.1
        """
        from agent_fox.engine.issue_summary import SourceIssue, parse_source_url

        prd_path = tmp_path / "prd.md"
        prd_path.write_text(
            "## Source\n\n"
            "Source: https://github.com/first/repo/issues/10\n\n"
            "## Source\n\n"
            "Source: https://github.com/second/repo/issues/20\n"
        )

        result = parse_source_url(prd_path)

        # Must return from the FIRST Source section, not raise
        assert result is not None
        assert isinstance(result, SourceIssue)
        assert result.issue_number == 10
        assert result.owner == "first"


# ---------------------------------------------------------------------------
# TS-108-6, TS-108-7
# Requirements: 108-REQ-3.1, 108-REQ-3.2, 108-REQ-3.3, 108-REQ-3.4
# ---------------------------------------------------------------------------


class TestBuildSummaryComment:
    """Tests for build_summary_comment() function."""

    def test_includes_required_fields(self, tmp_path: Path) -> None:
        """TS-108-6: build_summary_comment includes required fields.

        Requirements: 108-REQ-3.1, 108-REQ-3.2, 108-REQ-3.3, 108-REQ-3.4
        """
        from agent_fox.engine.issue_summary import build_summary_comment

        spec_name = "108_issue_session_summary"
        commit_sha = "abc123def"

        tasks_path = tmp_path / "tasks.md"
        tasks_path.write_text("## Tasks\n\n- [x] 1. Write failing tests\n- [x] 2. Implement feature\n")

        comment = build_summary_comment(spec_name, commit_sha, tasks_path)

        assert spec_name in comment, "Comment must contain spec name"
        assert commit_sha in comment, "Comment must contain commit SHA"
        assert "Write failing tests" in comment, "Comment must contain group 1 title"
        assert "Implement feature" in comment, "Comment must contain group 2 title"
        assert "*Auto-generated by agent-fox.*" in comment, "Comment must contain footer"

    def test_with_missing_tasks_file_still_has_required_fields(self, tmp_path: Path) -> None:
        """TS-108-7: build_summary_comment with non-existent tasks.md.

        Requirements: 108-REQ-3.1, 108-REQ-3.2, 108-REQ-3.4
        """
        from agent_fox.engine.issue_summary import build_summary_comment

        spec_name = "my_spec"
        commit_sha = "sha123"
        tasks_path = tmp_path / "nonexistent_tasks.md"  # does not exist

        # Must not raise
        comment = build_summary_comment(spec_name, commit_sha, tasks_path)

        assert spec_name in comment, "Comment must still contain spec name"
        assert commit_sha in comment, "Comment must still contain commit SHA"
        assert "*Auto-generated by agent-fox.*" in comment, "Comment must still contain footer"


# ---------------------------------------------------------------------------
# TS-108-8, TS-108-9, TS-108-10, TS-108-11
# Requirements: 108-REQ-2.1, 108-REQ-2.2, 108-REQ-2.E1, 108-REQ-4.1, 108-REQ-4.E1
# ---------------------------------------------------------------------------


class TestPostIssueSummaries:
    """Tests for post_issue_summaries() function."""

    def _make_spec_dir(self, base: Path, spec_name: str, issue_url: str) -> Path:
        """Create a minimal spec directory with prd.md and tasks.md."""
        spec_dir = base / spec_name
        spec_dir.mkdir(parents=True)
        (spec_dir / "prd.md").write_text(f"## Source\n\nSource: {issue_url}\n")
        (spec_dir / "tasks.md").write_text("- [x] 1. Implement feature\n")
        return spec_dir

    def _make_mock_platform(self, forge_type: str = "github") -> MagicMock:
        """Create a mock platform with the given forge type."""
        platform = MagicMock()
        platform.forge_type = forge_type
        platform.add_issue_comment = AsyncMock()
        return platform

    def _mock_git_sha(self, sha: str = "abc123") -> MagicMock:
        """Return a mock subprocess result for git rev-parse develop."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"{sha}\n"
        return mock_result

    @pytest.mark.asyncio
    async def test_posts_comment_for_completed_spec(self, tmp_path: Path) -> None:
        """TS-108-8: post_issue_summaries posts comment for completed spec.

        Requirements: 108-REQ-4.1, 108-REQ-2.1, 108-REQ-2.2
        """
        from agent_fox.engine.issue_summary import post_issue_summaries

        spec_name = "108_my_spec"
        specs_dir = tmp_path / "specs"
        self._make_spec_dir(specs_dir, spec_name, "https://github.com/owner/repo/issues/42")

        platform = self._make_mock_platform(forge_type="github")

        with patch("subprocess.run", return_value=self._mock_git_sha("abc123")):
            posted = await post_issue_summaries(
                platform=platform,
                specs_dir=specs_dir,
                completed_specs={spec_name},
                already_posted=set(),
                repo_root=tmp_path,
            )

        platform.add_issue_comment.assert_called_once()
        call_args = platform.add_issue_comment.call_args
        issue_number = call_args[0][0]
        body = call_args[0][1]
        assert issue_number == 42
        assert spec_name in body
        assert spec_name in posted

    @pytest.mark.asyncio
    async def test_skips_already_posted_specs(self, tmp_path: Path) -> None:
        """TS-108-9: post_issue_summaries skips already-posted specs.

        Requirements: 108-REQ-2.E1
        """
        from agent_fox.engine.issue_summary import post_issue_summaries

        spec_name = "108_my_spec"
        specs_dir = tmp_path / "specs"
        self._make_spec_dir(specs_dir, spec_name, "https://github.com/owner/repo/issues/42")

        platform = self._make_mock_platform(forge_type="github")

        with patch("subprocess.run", return_value=self._mock_git_sha()):
            posted = await post_issue_summaries(
                platform=platform,
                specs_dir=specs_dir,
                completed_specs={spec_name},
                already_posted={spec_name},  # already posted
                repo_root=tmp_path,
            )

        platform.add_issue_comment.assert_not_called()
        assert len(posted) == 0

    @pytest.mark.asyncio
    async def test_skips_spec_without_source_url(self, tmp_path: Path) -> None:
        """TS-108-10: post_issue_summaries skips spec without a valid source URL.

        Requirements: 108-REQ-1.E1, 108-REQ-1.E2
        """
        from agent_fox.engine.issue_summary import post_issue_summaries

        spec_name = "108_my_spec"
        specs_dir = tmp_path / "specs"
        spec_dir = specs_dir / spec_name
        spec_dir.mkdir(parents=True)
        # Non-URL source
        (spec_dir / "prd.md").write_text("## Source\n\nSource: Input provided by user via interactive prompt\n")
        (spec_dir / "tasks.md").write_text("- [x] 1. Feature\n")

        platform = self._make_mock_platform()

        with patch("subprocess.run", return_value=self._mock_git_sha()):
            posted = await post_issue_summaries(
                platform=platform,
                specs_dir=specs_dir,
                completed_specs={spec_name},
                already_posted=set(),
                repo_root=tmp_path,
            )

        platform.add_issue_comment.assert_not_called()
        assert len(posted) == 0

    @pytest.mark.asyncio
    async def test_handles_comment_posting_failure(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """TS-108-11: post_issue_summaries handles add_issue_comment failure.

        Requirements: 108-REQ-4.E1
        """
        from agent_fox.engine.issue_summary import post_issue_summaries

        spec_name = "108_my_spec"
        specs_dir = tmp_path / "specs"
        self._make_spec_dir(specs_dir, spec_name, "https://github.com/owner/repo/issues/42")

        platform = self._make_mock_platform(forge_type="github")
        platform.add_issue_comment = AsyncMock(side_effect=RuntimeError("network error"))

        with caplog.at_level(logging.WARNING), patch("subprocess.run", return_value=self._mock_git_sha()):
            posted = await post_issue_summaries(
                platform=platform,
                specs_dir=specs_dir,
                completed_specs={spec_name},
                already_posted=set(),
                repo_root=tmp_path,
            )

        # Must not propagate exception
        # Spec name must NOT be in posted (posting failed)
        assert spec_name not in posted
        # Warning must be logged
        assert any(r.levelno >= logging.WARNING for r in caplog.records)


# ---------------------------------------------------------------------------
# TS-108-17
# Requirements: 108-REQ-4.E2
# ---------------------------------------------------------------------------


class TestPostIssueSummariesForgeMismatch:
    """Tests for forge type mismatch handling in post_issue_summaries()."""

    @pytest.mark.asyncio
    async def test_skips_forge_mismatch(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """TS-108-17: post_issue_summaries skips when forge type doesn't match.

        Requirements: 108-REQ-4.E2
        """
        from agent_fox.engine.issue_summary import post_issue_summaries

        spec_name = "108_my_spec"
        specs_dir = tmp_path / "specs"
        spec_dir = specs_dir / spec_name
        spec_dir.mkdir(parents=True)
        # GitHub source URL — forge = "github"
        (spec_dir / "prd.md").write_text("## Source\n\nSource: https://github.com/owner/repo/issues/42\n")
        (spec_dir / "tasks.md").write_text("- [x] 1. Feature\n")

        # Platform is NOT github (simulating a GitLab platform)
        platform = MagicMock()
        platform.forge_type = "gitlab"  # mismatch with "github"
        platform.add_issue_comment = AsyncMock()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc123\n"

        with caplog.at_level(logging.INFO), patch("subprocess.run", return_value=mock_result):
            posted = await post_issue_summaries(
                platform=platform,
                specs_dir=specs_dir,
                completed_specs={spec_name},
                already_posted=set(),
                repo_root=tmp_path,
            )

        platform.add_issue_comment.assert_not_called()
        assert len(posted) == 0
        # Info-level message about forge mismatch must be logged
        assert any(r.levelno == logging.INFO for r in caplog.records)


# ---------------------------------------------------------------------------
# TS-108-15, TS-108-16
# Requirements: 108-REQ-6.1, 108-REQ-6.E1
# ---------------------------------------------------------------------------


class TestGetDevelopHead:
    """Tests for _get_develop_head() function."""

    def test_returns_sha_on_success(self, tmp_path: Path) -> None:
        """TS-108-15: _get_develop_head returns SHA on successful git call.

        Requirements: 108-REQ-6.1
        """
        from agent_fox.engine.issue_summary import _get_develop_head

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc123def456\n"

        with patch("subprocess.run", return_value=mock_result):
            sha = _get_develop_head(tmp_path)

        assert sha == "abc123def456"

    def test_returns_unknown_on_failure(self, tmp_path: Path) -> None:
        """TS-108-16: _get_develop_head returns 'unknown' when git fails.

        Requirements: 108-REQ-6.E1
        """
        from agent_fox.engine.issue_summary import _get_develop_head

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            sha = _get_develop_head(tmp_path)

        assert sha == "unknown"
