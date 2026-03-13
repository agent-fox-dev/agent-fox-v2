"""Tests for Skeptic archetype behavior.

Test Spec: TS-26-32 through TS-26-36, TS-26-E11
Requirements: 26-REQ-8.1 through 26-REQ-8.5, 26-REQ-8.E1
"""

from __future__ import annotations

import duckdb
import pytest

# ---------------------------------------------------------------------------
# TS-26-32: Skeptic produces review.md
# Requirement: 26-REQ-8.1
# ---------------------------------------------------------------------------


class TestSkepticTemplate:
    """Verify Skeptic template references severity categories and JSON output."""

    def test_template_has_severity_categories(self) -> None:
        import os

        template_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "agent_fox",
            "_templates",
            "prompts",
            "skeptic.md",
        )
        template_path = os.path.normpath(template_path)

        with open(template_path, encoding="utf-8") as f:
            content = f.read()

        content_lower = content.lower()
        assert "critical" in content_lower
        assert "major" in content_lower
        assert "minor" in content_lower
        assert "findings" in content_lower


# ---------------------------------------------------------------------------
# TS-26-33: Skeptic files GitHub issue
# Requirement: 26-REQ-8.2
# ---------------------------------------------------------------------------


class TestSkepticGithubIssue:
    """Verify Skeptic post-session logic files a GitHub issue."""

    @pytest.mark.asyncio
    async def test_skeptic_files_issue_with_search(self) -> None:
        from unittest.mock import AsyncMock

        from agent_fox.platform.github import IssueResult
        from agent_fox.session.github_issues import file_or_update_issue

        mock_platform = AsyncMock()
        mock_platform.search_issues.return_value = []
        mock_platform.create_issue.return_value = IssueResult(
            number=1,
            title="[Skeptic Review] 03_session",
            html_url="https://github.com/repo/issues/1",
        )

        result = await file_or_update_issue(
            "[Skeptic Review] 03_session",
            "## Critical\n- Issue found",
            platform=mock_platform,
        )

        assert result == "https://github.com/repo/issues/1"
        mock_platform.search_issues.assert_called_once()
        mock_platform.create_issue.assert_called_once()


# ---------------------------------------------------------------------------
# TS-26-34: Skeptic review passed to Coder as context
# Requirement: 26-REQ-8.3
# ---------------------------------------------------------------------------


class TestReviewPassedToCoder:
    """Verify Skeptic's review.md content is included in Coder's prompt."""

    def test_review_included_in_context(
        self,
        tmp_path: pytest.TempPathFactory,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        from agent_fox.session.prompt import assemble_context

        # Create a spec dir with a review.md
        spec_dir = tmp_path / ".specs" / "test_spec"  # type: ignore[operator]
        spec_dir.mkdir(parents=True)
        (spec_dir / "review.md").write_text(
            "## Critical\n- Missing edge case handling\n"
        )
        # requirements.md needed for assemble_context
        (spec_dir / "requirements.md").write_text("# Requirements\nTest req\n")

        context = assemble_context(spec_dir, task_group=1, conn=knowledge_conn)
        # 26-REQ-8.3: Skeptic review content is included in Coder context
        assert "Test req" in context
        assert "Missing edge case handling" in context


# ---------------------------------------------------------------------------
# TS-26-35: Skeptic blocking threshold
# Requirement: 26-REQ-8.4
# ---------------------------------------------------------------------------


class TestBlockingThreshold:
    """Verify Skeptic blocks only when critical count exceeds threshold."""

    def test_at_threshold_not_blocked(self) -> None:
        from agent_fox.session.convergence import Finding, converge_skeptic

        # 3 criticals with threshold=3 → NOT blocked
        findings = [Finding("critical", f"Issue {i}") for i in range(3)]
        _, blocked = converge_skeptic([findings], block_threshold=3)
        assert blocked is False

    def test_above_threshold_blocked(self) -> None:
        from agent_fox.session.convergence import Finding, converge_skeptic

        # 4 criticals with threshold=3 → blocked
        findings = [Finding("critical", f"Issue {i}") for i in range(4)]
        _, blocked = converge_skeptic([findings], block_threshold=3)
        assert blocked is True

    def test_zero_threshold_one_critical_blocks(self) -> None:
        from agent_fox.session.convergence import Finding, converge_skeptic

        findings = [Finding("critical", "Issue")]
        _, blocked = converge_skeptic([findings], block_threshold=0)
        assert blocked is True


# ---------------------------------------------------------------------------
# TS-26-36: Skeptic read-only allowlist
# Requirement: 26-REQ-8.5
# ---------------------------------------------------------------------------


class TestReadonlyAllowlist:
    """Verify Skeptic's default allowlist is read-only."""

    def test_contains_readonly_commands(self) -> None:
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["skeptic"]
        allowed = set(entry.default_allowlist or [])
        assert {"ls", "cat", "git", "wc", "head", "tail"}.issubset(allowed)

    def test_excludes_write_commands(self) -> None:
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["skeptic"]
        allowed = set(entry.default_allowlist or [])
        for cmd in ["rm", "mv", "cp", "mkdir", "make", "pytest"]:
            assert cmd not in allowed, f"Skeptic should not allow {cmd}"


# ---------------------------------------------------------------------------
# TS-26-E11: Skeptic closes issue when no critical findings
# Requirement: 26-REQ-8.E1
# ---------------------------------------------------------------------------


class TestCloseIssueNoFindings:
    """Verify existing Skeptic issue is closed when no critical findings."""

    @pytest.mark.asyncio
    async def test_close_if_empty(self) -> None:
        from unittest.mock import AsyncMock

        from agent_fox.platform.github import IssueResult
        from agent_fox.session.github_issues import file_or_update_issue

        existing = IssueResult(
            number=42,
            title="[Skeptic Review] spec",
            html_url="https://github.com/o/r/issues/42",
        )
        mock_platform = AsyncMock()
        mock_platform.search_issues.return_value = [existing]
        mock_platform.close_issue.return_value = None

        await file_or_update_issue(
            "[Skeptic Review] spec",
            "",  # empty body = no findings
            close_if_empty=True,
            platform=mock_platform,
        )

        # Verify close was called with the correct issue number
        mock_platform.close_issue.assert_called_once()
        call_args = mock_platform.close_issue.call_args
        assert call_args[0][0] == 42
