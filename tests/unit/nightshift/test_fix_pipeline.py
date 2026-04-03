"""Unit tests for fix pipeline: auto label, in-memory spec, branch naming, PR body.

Test Spec: TS-61-2, TS-61-16, TS-61-17, TS-61-21, TS-61-E2, TS-61-E9
Requirements: 61-REQ-1.2, 61-REQ-6.1, 61-REQ-6.2, 61-REQ-7.2, 61-REQ-1.E2,
              61-REQ-6.E2
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# TS-61-2: Auto flag assigns af:fix label
# Requirement: 61-REQ-1.2
# ---------------------------------------------------------------------------


class TestAutoFixLabel:
    """Verify that --auto causes created issues to get the af:fix label."""

    @pytest.mark.asyncio
    async def test_auto_assigns_label(self) -> None:
        """When auto_fix=True, platform.assign_label is called with 'af:fix'."""
        from unittest.mock import ANY, AsyncMock, MagicMock

        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None
        config.night_shift.categories.dependency_freshness = True
        config.night_shift.categories.todo_fixme = False
        config.night_shift.categories.test_coverage = False
        config.night_shift.categories.deprecated_api = False
        config.night_shift.categories.linter_debt = False
        config.night_shift.categories.dead_code = False
        config.night_shift.categories.documentation_drift = False

        mock_platform = AsyncMock()
        mock_platform.create_issue = AsyncMock(return_value=MagicMock(number=1, title="test", html_url="http://test"))
        mock_platform.assign_label = AsyncMock()

        engine = NightShiftEngine(config=config, platform=mock_platform, auto_fix=True)

        # Simulate a hunt scan that produces a finding
        from unittest.mock import patch

        from agent_fox.nightshift.finding import Finding

        mock_finding = Finding(
            category="dependency_freshness",
            title="Test finding",
            description="Test",
            severity="minor",
            affected_files=["test.py"],
            suggested_fix="Fix it",
            evidence="evidence",
            group_key="test-group",
        )

        with patch.object(
            engine,
            "_run_hunt_scan_inner",
            AsyncMock(return_value=[mock_finding]),
        ):
            await engine._run_hunt_scan()

        mock_platform.assign_label.assert_called_with(ANY, "af:fix")


# ---------------------------------------------------------------------------
# TS-61-16: In-memory spec from issue
# Requirement: 61-REQ-6.1
# ---------------------------------------------------------------------------


class TestInMemorySpec:
    """Verify that an in-memory spec is built from issue content."""

    def test_build_spec_from_issue(self) -> None:
        """InMemorySpec has populated fields from issue."""
        from agent_fox.nightshift.spec_builder import build_in_memory_spec
        from agent_fox.platform.github import IssueResult

        issue = IssueResult(
            number=42,
            title="Fix unused imports",
            html_url="https://github.com/test/repo/issues/42",
        )
        issue_body = "Remove unused imports in engine/ ..."
        spec = build_in_memory_spec(issue, issue_body)
        assert spec.issue_number == 42
        assert "unused imports" in spec.task_prompt.lower()
        assert spec.branch_name.startswith("fix/")

    def test_spec_has_system_context(self) -> None:
        """InMemorySpec contains the issue body as system context."""
        from agent_fox.nightshift.spec_builder import build_in_memory_spec
        from agent_fox.platform.github import IssueResult

        issue = IssueResult(
            number=10,
            title="Fix tests",
            html_url="https://github.com/test/repo/issues/10",
        )
        issue_body = "The test suite is failing due to import errors."
        spec = build_in_memory_spec(issue, issue_body)
        assert "import errors" in spec.system_context.lower()


# ---------------------------------------------------------------------------
# TS-61-17: Fix branch naming
# Requirement: 61-REQ-6.2
# ---------------------------------------------------------------------------


class TestBranchNaming:
    """Verify branch name is fix/{sanitised-title}."""

    def test_sanitise_special_characters(self) -> None:
        """Title with special chars is sanitised for branch name."""
        from agent_fox.nightshift.spec_builder import sanitise_branch_name

        branch = sanitise_branch_name("Fix: unused imports (engine/)")
        assert branch == "fix/fix-unused-imports-engine"
        # No extra slashes after "fix/"
        assert "/" not in branch[4:]

    def test_sanitise_spaces(self) -> None:
        """Spaces become hyphens."""
        from agent_fox.nightshift.spec_builder import sanitise_branch_name

        branch = sanitise_branch_name("fix the broken test")
        assert branch == "fix/fix-the-broken-test"

    def test_sanitise_uppercase(self) -> None:
        """Branch name is lowercased."""
        from agent_fox.nightshift.spec_builder import sanitise_branch_name

        branch = sanitise_branch_name("Fix Unused IMPORTS")
        assert branch == "fix/fix-unused-imports"


# ---------------------------------------------------------------------------
# TS-61-21: PR references originating issue
# Requirement: 61-REQ-7.2
# ---------------------------------------------------------------------------


class TestPRBody:
    """Verify that the PR body contains an issue reference."""

    def test_pr_body_references_issue(self) -> None:
        """PR body contains 'Fixes #42' or 'Closes #42'."""
        from agent_fox.nightshift.fix_pipeline import build_pr_body

        body = build_pr_body(issue_number=42, summary="Removed unused imports")
        assert "#42" in body
        assert "Fixes #42" in body or "Closes #42" in body


# ---------------------------------------------------------------------------
# TS-61-E2: Cost limit reached
# Requirement: 61-REQ-1.E2
# ---------------------------------------------------------------------------


class TestCostLimitReached:
    """Verify engine stops on cost limit."""

    def test_check_cost_limit_true(self) -> None:
        """_check_cost_limit returns True when cost exceeds max."""
        from unittest.mock import MagicMock

        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = 10.0
        config.orchestrator.max_sessions = None
        platform = MagicMock()

        engine = NightShiftEngine(config=config, platform=platform)
        engine.state.total_cost = 9.5
        assert engine._check_cost_limit() is True

    def test_check_cost_limit_false(self) -> None:
        """_check_cost_limit returns False when cost is under max."""
        from unittest.mock import MagicMock

        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = 10.0
        config.orchestrator.max_sessions = None
        platform = MagicMock()

        engine = NightShiftEngine(config=config, platform=platform)
        engine.state.total_cost = 5.0
        assert engine._check_cost_limit() is False


# ---------------------------------------------------------------------------
# Harvest and close: successful fix merges branch and closes issue
# ---------------------------------------------------------------------------


class TestSuccessfulFixHarvestsAndCloses:
    """Verify that a successful fix triggers harvest + push and closes the issue."""

    @pytest.mark.asyncio
    async def test_harvest_and_close_called_on_success(self) -> None:
        """After all sessions succeed, harvest/push runs and the issue is closed."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.github import IssueResult

        config = MagicMock()
        mock_platform = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)

        # Stub out the archetype sessions so they succeed without real work
        pipeline._run_session = AsyncMock(return_value=None)  # type: ignore[method-assign]
        pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]

        issue = IssueResult(
            number=7,
            title="Fix broken login",
            html_url="https://github.com/test/repo/issues/7",
        )

        with patch.object(pipeline, "_harvest_and_push", AsyncMock(return_value=True)) as mock_harvest:
            await pipeline.process_issue(issue, issue_body="Login is broken.")

        mock_harvest.assert_awaited_once()
        mock_platform.close_issue.assert_awaited_once()
        closed_num = mock_platform.close_issue.call_args[0][0]
        assert closed_num == 7

    @pytest.mark.asyncio
    async def test_issue_not_closed_on_harvest_failure(self) -> None:
        """When harvest/push fails, the issue is NOT closed."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.github import IssueResult

        config = MagicMock()
        mock_platform = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._run_session = AsyncMock(return_value=None)  # type: ignore[method-assign]
        pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]

        issue = IssueResult(
            number=9,
            title="Fix something else",
            html_url="https://github.com/test/repo/issues/9",
        )

        with patch.object(pipeline, "_harvest_and_push", AsyncMock(return_value=False)):
            await pipeline.process_issue(issue, issue_body="Something else is broken.")

        mock_platform.close_issue.assert_not_awaited()
        # A comment about manual merge should be posted
        comments = [str(call) for call in mock_platform.add_issue_comment.call_args_list]
        assert any("manual" in c.lower() or "merge" in c.lower() for c in comments)

    @pytest.mark.asyncio
    async def test_issue_not_closed_on_session_failure(self) -> None:
        """When a session raises, the issue is NOT closed."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.github import IssueResult

        config = MagicMock()
        mock_platform = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]
        pipeline._run_session = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("session boom")
        )

        issue = IssueResult(
            number=8,
            title="Fix something",
            html_url="https://github.com/test/repo/issues/8",
        )

        await pipeline.process_issue(issue, issue_body="Something is broken.")

        mock_platform.close_issue.assert_not_awaited()


# ---------------------------------------------------------------------------
# TS-61-E9: Empty issue body
# Requirement: 61-REQ-6.E2
# ---------------------------------------------------------------------------


class TestEmptyIssueBody:
    """Verify handling of empty issue body."""

    @pytest.mark.asyncio
    async def test_empty_body_posts_comment(self) -> None:
        """When issue body is empty, a comment requesting detail is posted."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.github import IssueResult

        config = MagicMock()
        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)

        issue = IssueResult(
            number=1,
            title="Fix something",
            html_url="https://github.com/test/repo/issues/1",
        )
        # Issue body is empty
        await pipeline.process_issue(issue, issue_body="")

        comments = [str(call) for call in mock_platform.add_issue_comment.call_args_list]
        assert any("detail" in c.lower() or "insufficient" in c.lower() for c in comments)


# ---------------------------------------------------------------------------
# Issue #226: HuntScanner wired to _run_hunt_scan_inner
# Issue #227: auto_fix uses returned issue list, never calls create_issue twice
# Issue #229: supersession_pairs acted on before processing loop
# ---------------------------------------------------------------------------


class TestHuntScanWiring:
    """_run_hunt_scan_inner delegates to HuntScanner, not a stub."""

    @pytest.mark.asyncio
    async def test_run_hunt_scan_inner_calls_hunt_scanner(self) -> None:
        """_run_hunt_scan_inner uses HuntScanner.run, not a hard-coded []."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.night_shift.categories = MagicMock()

        engine = NightShiftEngine(config=config, platform=AsyncMock())

        with patch("agent_fox.nightshift.hunt.HuntScanner") as MockScanner:
            mock_scanner_instance = MagicMock()
            mock_scanner_instance.run = AsyncMock(return_value=[])
            MockScanner.return_value = mock_scanner_instance

            await engine._run_hunt_scan_inner()

        mock_scanner_instance.run.assert_awaited_once()


class TestAutoFixNoDoubleCreate:
    """--auto labels already-created issues; never calls create_issue twice."""

    @pytest.mark.asyncio
    async def test_auto_fix_calls_create_issue_once_per_group(self) -> None:
        """With auto_fix=True, create_issue is called exactly once per group."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.engine import NightShiftEngine
        from agent_fox.nightshift.finding import Finding, FindingGroup

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        created_issue = MagicMock(number=99)
        mock_platform.create_issue = AsyncMock(return_value=created_issue)
        mock_platform.assign_label = AsyncMock()

        engine = NightShiftEngine(config=config, platform=mock_platform, auto_fix=True)

        finding = Finding(
            category="linter_debt",
            title="Test",
            description="desc",
            severity="minor",
            affected_files=[],
            suggested_fix="fix it",
            evidence="ev",
            group_key="key",
        )
        group = FindingGroup(findings=[finding], title="Test group", body="", category="linter_debt")

        with (
            patch.object(engine, "_run_hunt_scan_inner", AsyncMock(return_value=[finding])),
            patch(
                "agent_fox.nightshift.engine.consolidate_findings",
                AsyncMock(return_value=[group]),
            ),
        ):
            await engine._run_hunt_scan()

        # create_issue called exactly once (not twice)
        assert mock_platform.create_issue.await_count == 1
        # assign_label called with the issue number from that single create
        mock_platform.assign_label.assert_awaited_once_with(99, "af:fix")


class TestSupersessionPairsActedOn:
    """Engine closes AI-identified superseded issues before processing."""

    @pytest.mark.asyncio
    async def test_superseded_issue_closed_before_processing(self) -> None:
        """When triage returns supersession_pairs, the obsolete issue is closed."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.engine import NightShiftEngine
        from agent_fox.nightshift.triage import TriageResult
        from agent_fox.platform.github import IssueResult

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        mock_platform.close_issue = AsyncMock()

        issues = [
            IssueResult(number=10, title="Keep", html_url="", body="detail"),
            IssueResult(number=20, title="Superseded", html_url="", body="detail"),
            IssueResult(number=30, title="Third", html_url="", body="detail"),
        ]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)

        engine = NightShiftEngine(config=config, platform=mock_platform)
        engine._process_fix = AsyncMock()  # type: ignore[assignment]

        triage_result = TriageResult(
            processing_order=[10, 30],
            edges=[],
            supersession_pairs=[(10, 20)],  # 20 superseded by 10
        )

        with (
            patch(
                "agent_fox.nightshift.engine.run_batch_triage",
                AsyncMock(return_value=triage_result),
            ),
            patch(
                "agent_fox.nightshift.engine.check_staleness",
                AsyncMock(return_value=MagicMock(obsolete_issues=[], rationale={})),
            ),
            patch(
                "agent_fox.nightshift.engine.fetch_github_relationships",
                AsyncMock(return_value=[]),
            ),
        ):
            await engine._run_issue_check()

        # Issue 20 must be closed as superseded
        closed_numbers = [call.args[0] for call in mock_platform.close_issue.call_args_list]
        assert 20 in closed_numbers

    @pytest.mark.asyncio
    async def test_superseded_issue_not_processed(self) -> None:
        """A superseded issue is skipped by the processing loop."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.engine import NightShiftEngine
        from agent_fox.nightshift.triage import TriageResult
        from agent_fox.platform.github import IssueResult

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        mock_platform.close_issue = AsyncMock()

        issues = [
            IssueResult(number=10, title="Keep", html_url="", body="detail"),
            IssueResult(number=20, title="Superseded", html_url="", body="detail"),
            IssueResult(number=30, title="Third", html_url="", body="detail"),
        ]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)

        engine = NightShiftEngine(config=config, platform=mock_platform)
        process_fix = AsyncMock()
        engine._process_fix = process_fix  # type: ignore[assignment]

        triage_result = TriageResult(
            processing_order=[10, 30],
            edges=[],
            supersession_pairs=[(10, 20)],
        )

        with (
            patch(
                "agent_fox.nightshift.engine.run_batch_triage",
                AsyncMock(return_value=triage_result),
            ),
            patch(
                "agent_fox.nightshift.engine.check_staleness",
                AsyncMock(return_value=MagicMock(obsolete_issues=[], rationale={})),
            ),
            patch(
                "agent_fox.nightshift.engine.fetch_github_relationships",
                AsyncMock(return_value=[]),
            ),
        ):
            await engine._run_issue_check()

        # _process_fix must never be called for the superseded issue 20
        processed_numbers = [call.args[0].number for call in process_fix.call_args_list]
        assert 20 not in processed_numbers
