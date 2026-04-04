"""Unit tests for Finding, FindingGroup, consolidation, and issue body.

Test Spec: TS-61-9, TS-61-13, TS-61-15
Requirements: 61-REQ-3.3, 61-REQ-5.1, 61-REQ-5.3
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_fox.nightshift.finding import Finding


def _make_finding(**overrides: Any) -> Finding:
    """Create a Finding with sensible defaults, overridden as needed."""
    defaults: dict[str, Any] = {
        "category": "linter_debt",
        "title": "Unused imports in engine/",
        "description": "5 files contain unused imports.",
        "severity": "minor",
        "affected_files": ["agent_fox/engine/engine.py"],
        "suggested_fix": "Remove unused imports using ruff --fix",
        "evidence": "ruff output:\n...",
        "group_key": "unused-imports-engine",
    }
    defaults.update(overrides)
    return Finding(**defaults)


# ---------------------------------------------------------------------------
# TS-61-9: Hunt category interface contract
# Requirement: 61-REQ-3.3
# ---------------------------------------------------------------------------


class TestFindingContract:
    """Verify that Finding has all required fields."""

    def test_finding_has_required_fields(self) -> None:
        """Every Finding must have all required fields populated."""
        f = _make_finding()
        assert isinstance(f, Finding)
        assert f.category != ""
        assert f.title != ""
        assert f.description != ""
        assert f.severity in ("critical", "major", "minor", "info")
        assert f.group_key != ""
        assert isinstance(f.affected_files, list)

    def test_finding_is_frozen(self) -> None:
        """Finding should be immutable (frozen dataclass)."""
        import pytest

        f = _make_finding()
        with pytest.raises((AttributeError, TypeError)):
            f.title = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TS-61-15: Issue body contains required fields
# Requirement: 61-REQ-5.3
# ---------------------------------------------------------------------------


class TestIssueBody:
    """Verify that issue body includes category, severity, files, and fix."""

    def test_issue_body_contains_category(self) -> None:
        """Issue body contains the category name."""
        from agent_fox.nightshift.finding import FindingGroup, build_issue_body

        group = FindingGroup(
            findings=[_make_finding(category="linter_debt", severity="minor")],
            title="Linter debt in engine",
            body="",
            category="linter_debt",
        )
        body = build_issue_body(group)
        assert "linter_debt" in body

    def test_issue_body_contains_severity(self) -> None:
        """Issue body contains the severity level."""
        from agent_fox.nightshift.finding import FindingGroup, build_issue_body

        group = FindingGroup(
            findings=[_make_finding(severity="minor")],
            title="Test",
            body="",
            category="linter_debt",
        )
        body = build_issue_body(group)
        assert "minor" in body

    def test_issue_body_contains_files(self) -> None:
        """Issue body contains affected file paths."""
        from agent_fox.nightshift.finding import FindingGroup, build_issue_body

        group = FindingGroup(
            findings=[
                _make_finding(affected_files=["foo.py", "bar.py"]),
            ],
            title="Test",
            body="",
            category="linter_debt",
        )
        body = build_issue_body(group)
        assert "foo.py" in body

    def test_issue_body_contains_suggested_fix(self) -> None:
        """Issue body contains suggested remediation."""
        from agent_fox.nightshift.finding import FindingGroup, build_issue_body

        group = FindingGroup(
            findings=[_make_finding(suggested_fix="Run ruff --fix")],
            title="Test",
            body="",
            category="linter_debt",
        )
        body = build_issue_body(group)
        lower = body.lower()
        assert "suggested" in lower or "remediation" in lower or "fix" in lower


# ---------------------------------------------------------------------------
# Issue #227: create_issues_from_groups must return created issue objects
# so callers can label them without creating duplicates.
# ---------------------------------------------------------------------------


class TestCreateIssuesFromGroupsReturnsResults:
    """create_issues_from_groups returns the created IssueResult objects."""

    @pytest.mark.asyncio
    async def test_returns_created_issue_list(self) -> None:
        """Returns one entry per successfully created issue."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.finding import FindingGroup, create_issues_from_groups

        group = FindingGroup(
            findings=[_make_finding()],
            title="Test finding",
            body="",
            category="linter_debt",
        )
        mock_result = MagicMock(number=42)
        mock_platform = AsyncMock()
        mock_platform.create_issue = AsyncMock(return_value=mock_result)

        results = await create_issues_from_groups([group], mock_platform)

        assert len(results) == 1
        assert getattr(results[0], "number") == 42

    @pytest.mark.asyncio
    async def test_failed_creation_excluded_from_results(self) -> None:
        """Issues that fail to create are not included in the return list."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.finding import FindingGroup, create_issues_from_groups

        good_group = FindingGroup(
            findings=[_make_finding(title="Good")],
            title="Good",
            body="",
            category="linter_debt",
        )
        bad_group = FindingGroup(
            findings=[_make_finding(title="Bad")],
            title="Bad",
            body="",
            category="linter_debt",
        )

        good_result = MagicMock(number=1)
        mock_platform = AsyncMock()
        mock_platform.create_issue = AsyncMock(side_effect=[good_result, RuntimeError("API error")])

        results = await create_issues_from_groups([good_group, bad_group], mock_platform)

        assert len(results) == 1
        assert getattr(results[0], "number") == 1
