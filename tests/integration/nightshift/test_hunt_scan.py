"""Integration tests for hunt scan pipeline.

Test Spec: TS-61-10, TS-61-14, TS-61-E3, TS-61-E5, TS-61-E7
Requirements: 61-REQ-3.4, 61-REQ-5.2, 61-REQ-2.E1, 61-REQ-3.E1, 61-REQ-5.E1
"""

from __future__ import annotations

import time

import pytest


def _make_finding(**overrides: object) -> object:
    """Create a Finding with sensible defaults."""
    from agent_fox.nightshift.finding import Finding

    defaults = {
        "category": "linter_debt",
        "title": "Test finding",
        "description": "Test description",
        "severity": "minor",
        "affected_files": ["test.py"],
        "suggested_fix": "Fix it",
        "evidence": "evidence",
        "group_key": "test-group",
    }
    defaults.update(overrides)
    return Finding(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TS-61-10: Parallel category execution
# Requirement: 61-REQ-3.4
# ---------------------------------------------------------------------------


class TestParallelCategoryExecution:
    """Verify that independent hunt categories execute in parallel."""

    @pytest.mark.asyncio
    async def test_parallel_execution_timing(self) -> None:
        """3 categories each taking 0.1s complete in < 0.25s total."""
        import asyncio
        from pathlib import Path
        from unittest.mock import MagicMock

        from agent_fox.nightshift.hunt import HuntCategoryRegistry, HuntScanner

        config = MagicMock()
        # Enable all categories
        for name in [
            "dependency_freshness",
            "todo_fixme",
            "test_coverage",
            "deprecated_api",
            "linter_debt",
            "dead_code",
            "documentation_drift",
        ]:
            setattr(config.night_shift.categories, name, True)

        registry = HuntCategoryRegistry()

        # Replace categories with 3 slow mocks
        async def slow_detect(*args: object, **kwargs: object) -> list[object]:
            await asyncio.sleep(0.1)
            return []

        mock_cats = []
        for i, name in enumerate(["cat_a", "cat_b", "cat_c"]):
            mock = MagicMock()
            mock.name = name
            mock.detect = slow_detect
            mock_cats.append(mock)

        registry._categories = mock_cats

        # All names "enabled"
        scanner = HuntScanner(registry, config)

        start = time.monotonic()
        await scanner.run(Path("/tmp/test"))
        elapsed = time.monotonic() - start

        # If parallel, should be ~0.1s, not 0.3s
        assert elapsed < 0.25


# ---------------------------------------------------------------------------
# TS-61-14: One issue per finding group
# Requirement: 61-REQ-5.2
# ---------------------------------------------------------------------------


class TestIssueCreation:
    """Verify that exactly one platform issue is created per group."""

    @pytest.mark.asyncio
    async def test_one_issue_per_group(self) -> None:
        """3 finding groups produce 3 platform issues."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.finding import (
            FindingGroup,
            create_issues_from_groups,
        )

        mock_platform = AsyncMock()
        mock_platform.create_issue = AsyncMock(
            return_value=MagicMock(number=1, title="t", html_url="http://x")
        )

        groups = [
            FindingGroup(
                findings=[_make_finding(group_key=f"g{i}")],
                title=f"Group {i}",
                body=f"Body {i}",
                category="linter_debt",
            )
            for i in range(3)
        ]

        await create_issues_from_groups(groups, mock_platform)
        assert mock_platform.create_issue.call_count == 3


# ---------------------------------------------------------------------------
# TS-61-E3: Platform API temporarily unavailable
# Requirement: 61-REQ-2.E1
# ---------------------------------------------------------------------------


class TestPlatformAPIUnavailable:
    """Verify graceful handling of platform API failure."""

    @pytest.mark.asyncio
    async def test_no_crash_on_api_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Warning logged, no crash, on platform API failure."""
        import logging
        from unittest.mock import AsyncMock, MagicMock

        import httpx
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None

        mock_platform = AsyncMock()
        mock_platform.list_issues_by_label = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )

        engine = NightShiftEngine(config=config, platform=mock_platform)

        with caplog.at_level(logging.WARNING):
            await engine._run_issue_check()  # should not raise

        assert "warning" in caplog.text.lower() or "error" in caplog.text.lower()


# ---------------------------------------------------------------------------
# TS-61-E5: Hunt category agent failure
# Requirement: 61-REQ-3.E1
# ---------------------------------------------------------------------------


class TestCategoryFailureIsolation:
    """Verify that a failing category does not block others."""

    @pytest.mark.asyncio
    async def test_other_categories_still_produce_findings(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When category B fails, A and C still produce findings."""
        import logging
        from pathlib import Path
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.hunt import HuntCategoryRegistry, HuntScanner

        config = MagicMock()
        for name in [
            "dependency_freshness",
            "todo_fixme",
            "test_coverage",
            "deprecated_api",
            "linter_debt",
            "dead_code",
            "documentation_drift",
        ]:
            setattr(config.night_shift.categories, name, True)

        finding_a = _make_finding(category="cat_a", group_key="a")
        finding_c = _make_finding(category="cat_c", group_key="c")

        mock_a = MagicMock()
        mock_a.name = "cat_a"
        mock_a.detect = AsyncMock(return_value=[finding_a])

        mock_b = MagicMock()
        mock_b.name = "cat_b"
        mock_b.detect = AsyncMock(side_effect=RuntimeError("agent timeout"))

        mock_c = MagicMock()
        mock_c.name = "cat_c"
        mock_c.detect = AsyncMock(return_value=[finding_c])

        registry = HuntCategoryRegistry()
        registry._categories = [mock_a, mock_b, mock_c]

        scanner = HuntScanner(registry, config)

        with caplog.at_level(logging.WARNING):
            findings = await scanner.run(Path("/tmp/test"))

        assert len(findings) == 2
        assert "RuntimeError" in caplog.text or "agent timeout" in caplog.text


# ---------------------------------------------------------------------------
# TS-61-E7: Issue creation failure
# Requirement: 61-REQ-5.E1
# ---------------------------------------------------------------------------


class TestIssueCreationFailure:
    """Verify that issue creation failure does not block other findings."""

    @pytest.mark.asyncio
    async def test_first_fails_second_succeeds(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """First group's issue creation fails, second succeeds."""
        import logging
        from unittest.mock import AsyncMock, MagicMock

        import httpx
        from agent_fox.nightshift.finding import (
            FindingGroup,
            create_issues_from_groups,
        )

        mock_platform = AsyncMock()
        mock_platform.create_issue = AsyncMock(
            side_effect=[
                httpx.HTTPError("fail"),
                MagicMock(number=2, title="t", html_url="http://x"),
            ]
        )

        groups = [
            FindingGroup(
                findings=[_make_finding(group_key="g1")],
                title="Group 1",
                body="Body 1",
                category="linter_debt",
            ),
            FindingGroup(
                findings=[_make_finding(group_key="g2")],
                title="Group 2",
                body="Body 2",
                category="dead_code",
            ),
        ]

        with caplog.at_level(logging.WARNING):
            await create_issues_from_groups(groups, mock_platform)

        assert mock_platform.create_issue.call_count == 2
        assert "fail" in caplog.text.lower()
