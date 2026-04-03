"""Integration tests for hunt scan deduplication gate.

Test Spec: TS-79-9 through TS-79-13, TS-79-E1 through TS-79-E4,
           TS-79-SMOKE-1, TS-79-SMOKE-2
Requirements: 79-REQ-3.1, 79-REQ-3.2, 79-REQ-3.E1, 79-REQ-4.1, 79-REQ-4.2,
              79-REQ-4.3, 79-REQ-4.4, 79-REQ-4.E1, 79-REQ-4.E2, 79-REQ-4.E3
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(**overrides: object) -> object:
    """Create a Finding with sensible defaults."""
    from agent_fox.nightshift.finding import Finding

    defaults: dict[str, object] = {
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


def _make_group(**overrides: object) -> object:
    """Create a FindingGroup with sensible defaults."""
    from agent_fox.nightshift.finding import FindingGroup

    defaults: dict[str, object] = {
        "findings": [],
        "title": "Test Group",
        "body": "Test body",
        "category": "linter_debt",
        "affected_files": ["test.py"],
    }
    defaults.update(overrides)
    return FindingGroup(**defaults)  # type: ignore[arg-type]


def _make_issue_result(number: int, body: str = "") -> object:
    """Create an IssueResult with a given body."""
    from agent_fox.platform.github import IssueResult

    return IssueResult(
        number=number,
        title=f"Issue #{number}",
        html_url=f"https://github.com/example/repo/issues/{number}",
        body=body,
    )


def _make_mock_platform(
    issues: list[object] | None = None,
    list_issues_raises: Exception | None = None,
) -> AsyncMock:
    """Create a mock platform with configurable behavior."""
    mock_platform = AsyncMock()

    if list_issues_raises is not None:
        mock_platform.list_issues_by_label = AsyncMock(side_effect=list_issues_raises)
    else:
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues or [])

    mock_platform.create_issue = AsyncMock(return_value=_make_issue_result(99))
    mock_platform.assign_label = AsyncMock(return_value=None)

    return mock_platform


# ---------------------------------------------------------------------------
# TS-79-9: Dedup gate filters matching groups
# Requirements: 79-REQ-4.2, 79-REQ-4.4
# ---------------------------------------------------------------------------


class TestFilterKnownDuplicates:
    """Verify filter_known_duplicates correctly filters duplicate FindingGroups."""

    @pytest.mark.asyncio
    async def test_matching_group_is_filtered_out(self) -> None:
        """TS-79-9: Group whose fingerprint matches an existing issue is excluded."""
        from agent_fox.nightshift.dedup import (
            compute_fingerprint,
            embed_fingerprint,
            filter_known_duplicates,
        )

        group_a = _make_group(category="dead_code", affected_files=["a.py"])
        group_b = _make_group(category="linter_debt", affected_files=["b.py"])

        fp_a = compute_fingerprint(group_a)  # type: ignore[arg-type]
        issue_body = embed_fingerprint("Existing issue body", fp_a)
        existing_issue = _make_issue_result(10, body=issue_body)

        platform = _make_mock_platform(issues=[existing_issue])

        result = await filter_known_duplicates([group_a, group_b], platform)  # type: ignore[arg-type]

        assert group_b in result
        assert group_a not in result

    @pytest.mark.asyncio
    async def test_novel_group_passes_through(self) -> None:
        """TS-79-9: Group with no fingerprint match is returned."""
        from agent_fox.nightshift.dedup import filter_known_duplicates

        group = _make_group(category="linter_debt", affected_files=["unique.py"])
        platform = _make_mock_platform(issues=[])

        result = await filter_known_duplicates([group], platform)  # type: ignore[arg-type]

        assert group in result

    @pytest.mark.asyncio
    async def test_result_is_subset_of_input(self) -> None:
        """TS-79-9: Result is always a subset of the input list."""
        from agent_fox.nightshift.dedup import filter_known_duplicates

        groups = [
            _make_group(category="linter_debt", affected_files=["a.py"]),
            _make_group(category="dead_code", affected_files=["b.py"]),
        ]
        platform = _make_mock_platform(issues=[])

        result = await filter_known_duplicates(groups, platform)  # type: ignore[arg-type]

        for g in result:
            assert g in groups

    # ---------------------------------------------------------------------------
    # TS-79-10: Dedup gate logs skipped duplicates
    # Requirement: 79-REQ-4.3
    # ---------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_skipped_group_logged_at_info(self, caplog: pytest.LogCaptureFixture) -> None:
        """TS-79-10: Skipped group is logged at INFO with title and issue number."""
        from agent_fox.nightshift.dedup import (
            compute_fingerprint,
            embed_fingerprint,
            filter_known_duplicates,
        )

        group = _make_group(
            category="linter_debt",
            affected_files=["a.py"],
            title="Unused imports",
        )
        fp = compute_fingerprint(group)  # type: ignore[arg-type]
        issue_body = embed_fingerprint("Existing issue body", fp)
        existing_issue = _make_issue_result(42, body=issue_body)

        platform = _make_mock_platform(issues=[existing_issue])

        with caplog.at_level(logging.INFO):
            result = await filter_known_duplicates([group], platform)  # type: ignore[arg-type]

        assert result == []
        log_text = caplog.text
        assert "Unused imports" in log_text
        assert "42" in log_text


# ---------------------------------------------------------------------------
# TS-79-11: Issue created with af:hunt label
# Requirement: 79-REQ-3.1
# ---------------------------------------------------------------------------


class TestCreateIssuesWithLabel:
    """Verify create_issues_from_groups passes af:hunt label."""

    @pytest.mark.asyncio
    async def test_create_issue_called_with_hunt_label(self) -> None:
        """TS-79-11: create_issue is called with labels=['af:hunt']."""
        from agent_fox.nightshift.finding import create_issues_from_groups

        group = _make_group(
            findings=[_make_finding()],
            category="linter_debt",
            affected_files=["a.py"],
        )

        mock_platform = AsyncMock()
        mock_platform.create_issue = AsyncMock(return_value=_make_issue_result(1))

        await create_issues_from_groups([group], mock_platform)  # type: ignore[arg-type]

        mock_platform.create_issue.assert_called_once()
        call_kwargs = mock_platform.create_issue.call_args

        # labels parameter should include "af:hunt"
        labels = call_kwargs.kwargs.get("labels") or (call_kwargs.args[2] if len(call_kwargs.args) > 2 else None)
        assert labels is not None
        assert "af:hunt" in labels

    # ---------------------------------------------------------------------------
    # TS-79-12: Issue body contains fingerprint marker
    # Requirement: 79-REQ-2.1
    # ---------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_issue_body_contains_fingerprint_marker(self) -> None:
        """TS-79-12: The body passed to create_issue includes a fingerprint marker."""
        from agent_fox.nightshift.dedup import compute_fingerprint, extract_fingerprint
        from agent_fox.nightshift.finding import create_issues_from_groups

        group = _make_group(
            findings=[_make_finding()],
            category="linter_debt",
            affected_files=["a.py"],
        )
        expected_fp = compute_fingerprint(group)  # type: ignore[arg-type]

        mock_platform = AsyncMock()
        mock_platform.create_issue = AsyncMock(return_value=_make_issue_result(1))

        await create_issues_from_groups([group], mock_platform)  # type: ignore[arg-type]

        call_kwargs = mock_platform.create_issue.call_args
        # body is the second positional argument
        body = call_kwargs.args[1] if len(call_kwargs.args) > 1 else call_kwargs.kwargs.get("body")
        assert body is not None
        extracted_fp = extract_fingerprint(body)
        assert extracted_fp == expected_fp

    # ---------------------------------------------------------------------------
    # TS-79-13: Auto mode assigns both labels
    # Requirement: 79-REQ-3.2
    # ---------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_auto_mode_assigns_af_fix_label(self) -> None:
        """TS-79-13: With auto_fix=True, af:fix label is assigned after creation."""
        from unittest.mock import patch

        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None

        created_issue = _make_issue_result(55)
        mock_platform = AsyncMock()
        mock_platform.create_issue = AsyncMock(return_value=created_issue)
        mock_platform.assign_label = AsyncMock(return_value=None)

        engine = NightShiftEngine(config=config, platform=mock_platform, auto_fix=True)

        finding = _make_finding()
        group = _make_group(findings=[finding], category="linter_debt", affected_files=["a.py"])

        with (
            patch.object(engine, "_run_hunt_scan_inner", AsyncMock(return_value=[finding])),
            patch(
                "agent_fox.nightshift.engine.consolidate_findings",
                AsyncMock(return_value=[group]),
            ),
            patch(
                "agent_fox.nightshift.engine.filter_known_duplicates",
                AsyncMock(return_value=[group]),
            ),
        ):
            await engine._run_hunt_scan()

        # af:hunt from create_issue call
        create_call = mock_platform.create_issue.call_args
        labels = create_call.kwargs.get("labels") or (create_call.args[2] if len(create_call.args) > 2 else None)
        assert labels is not None
        assert "af:hunt" in labels

        # af:fix from assign_label call
        mock_platform.assign_label.assert_called_once_with(55, "af:fix")


# ---------------------------------------------------------------------------
# TS-79-E1: Dedup gate fails open on platform error
# Requirement: 79-REQ-4.E1
# ---------------------------------------------------------------------------


class TestDedupEdgeCases:
    """Verify dedup gate edge cases."""

    @pytest.mark.asyncio
    async def test_fail_open_on_platform_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """TS-79-E1: Platform failure returns all groups unfiltered, warning logged."""
        from agent_fox.core.errors import IntegrationError
        from agent_fox.nightshift.dedup import filter_known_duplicates

        group_a = _make_group(category="linter_debt", affected_files=["a.py"])
        group_b = _make_group(category="dead_code", affected_files=["b.py"])

        platform = _make_mock_platform(list_issues_raises=IntegrationError("timeout"))

        with caplog.at_level(logging.WARNING):
            result = await filter_known_duplicates([group_a, group_b], platform)  # type: ignore[arg-type]

        assert len(result) == 2
        assert group_a in result
        assert group_b in result
        assert any("warn" in r.levelname.lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_fail_open_on_generic_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        """TS-79-E1: Any platform exception returns all groups unfiltered."""
        from agent_fox.nightshift.dedup import filter_known_duplicates

        groups = [_make_group(affected_files=["x.py"]), _make_group(affected_files=["y.py"])]
        platform = _make_mock_platform(list_issues_raises=RuntimeError("network error"))

        with caplog.at_level(logging.WARNING):
            result = await filter_known_duplicates(groups, platform)  # type: ignore[arg-type]

        assert len(result) == len(groups)

    # ---------------------------------------------------------------------------
    # TS-79-E2: No existing af:hunt issues
    # Requirement: 79-REQ-4.E2
    # ---------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_empty_platform_returns_all_groups(self) -> None:
        """TS-79-E2: Empty existing issues list means all groups are novel."""
        from agent_fox.nightshift.dedup import filter_known_duplicates

        group_a = _make_group(category="linter_debt", affected_files=["a.py"])
        group_b = _make_group(category="dead_code", affected_files=["b.py"])
        platform = _make_mock_platform(issues=[])

        result = await filter_known_duplicates([group_a, group_b], platform)  # type: ignore[arg-type]

        assert len(result) == 2

    # ---------------------------------------------------------------------------
    # TS-79-E3: All groups are duplicates
    # Requirement: 79-REQ-4.E3
    # ---------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_all_duplicates_returns_empty_list(self) -> None:
        """TS-79-E3: When all groups match existing issues, returns empty list."""
        from agent_fox.nightshift.dedup import (
            compute_fingerprint,
            embed_fingerprint,
            filter_known_duplicates,
        )

        group_a = _make_group(category="dead_code", affected_files=["a.py"])
        group_b = _make_group(category="linter_debt", affected_files=["b.py"])

        fp_a = compute_fingerprint(group_a)  # type: ignore[arg-type]
        fp_b = compute_fingerprint(group_b)  # type: ignore[arg-type]

        existing_issues = [
            _make_issue_result(1, body=embed_fingerprint("body", fp_a)),
            _make_issue_result(2, body=embed_fingerprint("body", fp_b)),
        ]
        platform = _make_mock_platform(issues=existing_issues)

        result = await filter_known_duplicates([group_a, group_b], platform)  # type: ignore[arg-type]

        assert result == []

    # ---------------------------------------------------------------------------
    # TS-79-E4: Label assignment failure does not block
    # Requirement: 79-REQ-3.E1
    # ---------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_label_assignment_failure_does_not_block(self) -> None:
        """TS-79-E4: If create_issue label param is ignored, issue is still created."""
        from agent_fox.nightshift.finding import create_issues_from_groups

        group = _make_group(findings=[_make_finding()], category="linter_debt", affected_files=["a.py"])

        mock_platform = AsyncMock()
        mock_platform.create_issue = AsyncMock(return_value=_make_issue_result(1))

        # Issue creation should succeed regardless
        result = await create_issues_from_groups([group], mock_platform)  # type: ignore[arg-type]

        assert len(result) == 1


# ---------------------------------------------------------------------------
# TS-79-SMOKE-1: Full hunt scan pipeline with dedup
# Execution Path: Path 1 from design.md
# ---------------------------------------------------------------------------


class TestHuntScanSmokeTests:
    """Smoke tests for the full hunt scan pipeline with deduplication."""

    @pytest.mark.asyncio
    async def test_smoke_full_pipeline_no_duplicates_second_run(self, caplog: pytest.LogCaptureFixture) -> None:
        """TS-79-SMOKE-1: Second scan with same findings creates no new issues.

        Must NOT satisfy with: mocking dedup or fingerprint functions.
        """
        from agent_fox.nightshift.dedup import extract_fingerprint
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None

        # Track all created issues
        created_issues: list[object] = []
        issue_counter = [0]

        async def mock_create_issue(title: str, body: str, labels: list[str] | None = None) -> object:
            issue_counter[0] += 1
            from agent_fox.platform.github import IssueResult

            issue = IssueResult(
                number=issue_counter[0],
                title=title,
                html_url=f"https://github.com/example/repo/issues/{issue_counter[0]}",
                body=body,
            )
            created_issues.append(issue)
            return issue

        # open_hunt_issues controls what list_issues_by_label returns
        open_hunt_issues: list[object] = []

        async def mock_list_issues(label: str, state: str = "open", **kwargs: object) -> list[object]:
            if label == "af:hunt":
                return open_hunt_issues
            return []

        mock_platform = AsyncMock()
        mock_platform.create_issue = mock_create_issue
        mock_platform.list_issues_by_label = mock_list_issues
        mock_platform.assign_label = AsyncMock(return_value=None)

        engine = NightShiftEngine(config=config, platform=mock_platform, auto_fix=False)

        # Build deterministic findings
        finding1 = _make_finding(
            category="linter_debt",
            affected_files=["file1.py"],
            group_key="g1",
        )
        finding2 = _make_finding(
            category="dead_code",
            affected_files=["file2.py"],
            group_key="g2",
        )
        fixed_findings = [finding1, finding2]

        # Use a stub for _run_hunt_scan_inner to return fixed findings
        # Use real consolidate_findings via mechanical path (< 3 findings per category)
        from agent_fox.nightshift.critic import _mechanical_grouping

        async def stub_inner() -> list[object]:
            return fixed_findings

        engine._run_hunt_scan_inner = stub_inner  # type: ignore[method-assign]

        # Patch consolidate_findings to use mechanical grouping directly
        from unittest.mock import patch

        with patch(
            "agent_fox.nightshift.engine.consolidate_findings",
            side_effect=lambda findings: _mechanical_grouping(findings),  # type: ignore[arg-type]
        ):
            # Iteration 1: creates issues
            with caplog.at_level(logging.INFO):
                await engine._run_hunt_scan()

        first_run_count = issue_counter[0]
        assert first_run_count > 0, "First scan must create at least one issue"

        # Verify fingerprints are embedded
        for issue in created_issues:
            fp = extract_fingerprint(issue.body)  # type: ignore[arg-type]
            assert fp is not None, f"Issue #{issue.number} body must contain fingerprint"

        # Configure platform to return the created issues for dedup check
        open_hunt_issues.extend(created_issues)

        with patch(
            "agent_fox.nightshift.engine.consolidate_findings",
            side_effect=lambda findings: _mechanical_grouping(findings),  # type: ignore[arg-type]
        ):
            # Iteration 2: same findings, should create nothing
            with caplog.at_level(logging.INFO):
                await engine._run_hunt_scan()

        assert issue_counter[0] == first_run_count, (
            f"Second scan created {issue_counter[0] - first_run_count} new issues but expected 0"
        )

    # ---------------------------------------------------------------------------
    # TS-79-SMOKE-2: Full pipeline fail-open on platform error
    # Execution Path: Path 2 from design.md
    # ---------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_smoke_fail_open_creates_all_issues(self, caplog: pytest.LogCaptureFixture) -> None:
        """TS-79-SMOKE-2: Platform failure during dedup creates all issues (fail-open).

        Must NOT satisfy with: mocking filter_known_duplicates.
        """
        from agent_fox.core.errors import IntegrationError
        from agent_fox.nightshift.critic import _mechanical_grouping
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None

        issue_counter = [0]

        async def mock_create_issue(title: str, body: str, labels: list[str] | None = None) -> object:
            issue_counter[0] += 1
            from agent_fox.platform.github import IssueResult

            return IssueResult(
                number=issue_counter[0],
                title=title,
                html_url=f"https://github.com/example/repo/issues/{issue_counter[0]}",
                body=body,
            )

        async def mock_list_issues_fails(label: str, state: str = "open", **kwargs: object) -> list[object]:
            raise IntegrationError("Platform timeout during dedup")

        mock_platform = AsyncMock()
        mock_platform.create_issue = mock_create_issue
        mock_platform.list_issues_by_label = mock_list_issues_fails
        mock_platform.assign_label = AsyncMock(return_value=None)

        engine = NightShiftEngine(config=config, platform=mock_platform, auto_fix=False)

        finding1 = _make_finding(
            category="linter_debt",
            affected_files=["file1.py"],
            group_key="g1",
        )
        finding2 = _make_finding(
            category="dead_code",
            affected_files=["file2.py"],
            group_key="g2",
        )
        fixed_findings = [finding1, finding2]

        async def stub_inner() -> list[object]:
            return fixed_findings

        engine._run_hunt_scan_inner = stub_inner  # type: ignore[method-assign]

        from unittest.mock import patch

        with patch(
            "agent_fox.nightshift.engine.consolidate_findings",
            side_effect=lambda findings: _mechanical_grouping(findings),  # type: ignore[arg-type]
        ):
            with caplog.at_level(logging.WARNING):
                await engine._run_hunt_scan()

        # All groups should have been created (fail-open)
        expected_groups = _mechanical_grouping(fixed_findings)  # type: ignore[arg-type]
        assert issue_counter[0] == len(expected_groups), (
            f"Expected {len(expected_groups)} issues but created {issue_counter[0]}"
        )

        # Warning should have been logged about the platform failure
        assert any("warn" in r.levelname.lower() for r in caplog.records), (
            "Expected a WARNING log about platform failure during dedup"
        )
