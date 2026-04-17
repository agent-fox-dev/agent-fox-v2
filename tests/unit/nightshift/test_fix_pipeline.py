"""Unit tests for fix pipeline: auto label, in-memory spec, branch naming, PR body.

Test Spec: TS-61-2, TS-61-16, TS-61-17, TS-61-21, TS-61-E2, TS-61-E9
Requirements: 61-REQ-1.2, 61-REQ-6.1, 61-REQ-6.2, 61-REQ-7.2, 61-REQ-1.E2,
              61-REQ-6.E2
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.workspace import WorkspaceInfo


def _mock_workspace() -> WorkspaceInfo:
    return WorkspaceInfo(
        path=Path("/tmp/mock-worktree"),
        branch="fix/test-branch",
        spec_name="fix-issue-42",
        task_group=0,
    )


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
        from agent_fox.platform.protocol import IssueResult

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
        from agent_fox.platform.protocol import IssueResult

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
# Session limit reached
# Requirement: 61-REQ-9.3
# ---------------------------------------------------------------------------


class TestSessionLimitReached:
    """Verify engine stops on session limit."""

    def test_check_session_limit_true(self) -> None:
        """_check_session_limit returns True when sessions >= max."""
        from unittest.mock import MagicMock

        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = 5
        platform = MagicMock()

        engine = NightShiftEngine(config=config, platform=platform)
        engine.state.total_sessions = 5
        assert engine._check_session_limit() is True

    def test_check_session_limit_false(self) -> None:
        """_check_session_limit returns False when sessions under max."""
        from unittest.mock import MagicMock

        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = 10
        platform = MagicMock()

        engine = NightShiftEngine(config=config, platform=platform)
        engine.state.total_sessions = 3
        assert engine._check_session_limit() is False

    def test_check_session_limit_unconfigured(self) -> None:
        """_check_session_limit returns False when max_sessions is None."""
        from unittest.mock import MagicMock

        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None
        platform = MagicMock()

        engine = NightShiftEngine(config=config, platform=platform)
        engine.state.total_sessions = 100
        assert engine._check_session_limit() is False


# ---------------------------------------------------------------------------
# Harvest and close: successful fix merges branch and closes issue
# ---------------------------------------------------------------------------


class TestSuccessfulFixHarvestsAndCloses:
    """Verify that a successful fix triggers harvest + push and closes the issue."""

    @pytest.mark.asyncio
    async def test_harvest_and_close_called_on_success(self) -> None:
        """After all sessions succeed, harvest/push runs and the issue is closed."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.protocol import IssueResult

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3
        mock_platform = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        triage_response = json.dumps(
            {
                "summary": "s",
                "affected_files": [],
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "d", "preconditions": "p", "expected": "e", "assertion": "a"},
                ],
            }
        )
        review_response = json.dumps(
            {
                "verdicts": [{"criterion_id": "AC-1", "verdict": "PASS", "evidence": "ok"}],
                "overall_verdict": "PASS",
                "summary": "ok",
            }
        )

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            outcome = MagicMock(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
            if archetype == "maintainer":
                outcome.response = triage_response
            elif archetype == "reviewer":
                outcome.response = review_response
            else:
                outcome.response = ""
            return outcome

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        issue = IssueResult(
            number=7,
            title="Fix broken login",
            html_url="https://github.com/test/repo/issues/7",
        )

        with patch.object(pipeline, "_harvest_and_push", AsyncMock(return_value="merged")) as mock_harvest:
            await pipeline.process_issue(issue, issue_body="Login is broken.")

        mock_harvest.assert_awaited_once()
        mock_platform.close_issue.assert_awaited_once()
        closed_num = mock_platform.close_issue.call_args[0][0]
        assert closed_num == 7

    @pytest.mark.asyncio
    async def test_issue_not_closed_on_harvest_failure(self) -> None:
        """When harvest/push fails, the issue is NOT closed."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.protocol import IssueResult

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3
        mock_platform = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        triage_response = json.dumps(
            {
                "summary": "s",
                "affected_files": [],
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "d", "preconditions": "p", "expected": "e", "assertion": "a"},
                ],
            }
        )
        review_response = json.dumps(
            {
                "verdicts": [{"criterion_id": "AC-1", "verdict": "PASS", "evidence": "ok"}],
                "overall_verdict": "PASS",
                "summary": "ok",
            }
        )

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            outcome = MagicMock(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
            if archetype == "maintainer":
                outcome.response = triage_response
            elif archetype == "reviewer":
                outcome.response = review_response
            else:
                outcome.response = ""
            return outcome

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        issue = IssueResult(
            number=9,
            title="Fix something else",
            html_url="https://github.com/test/repo/issues/9",
        )

        with patch.object(pipeline, "_harvest_and_push", AsyncMock(return_value="error")):
            await pipeline.process_issue(issue, issue_body="Something else is broken.")

        mock_platform.close_issue.assert_not_awaited()
        # A comment about manual investigation should be posted
        comments = [str(call) for call in mock_platform.add_issue_comment.call_args_list]
        assert any("manual" in c.lower() or "merge" in c.lower() for c in comments)

    @pytest.mark.asyncio
    async def test_issue_closed_when_harvest_returns_empty_and_review_passed(self) -> None:
        """When reviewer PASS but harvest has no new commits, issue IS closed.

        The fix is already present on develop — the issue should be closed
        to prevent the night-shift from endlessly re-processing it.
        """
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.protocol import IssueResult

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3
        mock_platform = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        triage_response = json.dumps(
            {
                "summary": "s",
                "affected_files": [],
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "d", "preconditions": "p", "expected": "e", "assertion": "a"},
                ],
            }
        )
        review_response = json.dumps(
            {
                "verdicts": [{"criterion_id": "AC-1", "verdict": "PASS", "evidence": "ok"}],
                "overall_verdict": "PASS",
                "summary": "ok",
            }
        )

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            outcome = MagicMock(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
            if archetype == "maintainer":
                outcome.response = triage_response
            elif archetype == "reviewer":
                outcome.response = review_response
            else:
                outcome.response = ""
            return outcome

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        issue = IssueResult(
            number=11,
            title="Fix empty harvest",
            html_url="https://github.com/test/repo/issues/11",
        )

        # harvest() returns [] (no new commits), post_harvest_integrate succeeds
        with (
            patch("agent_fox.workspace.harvest.harvest", AsyncMock(return_value=[])),
            patch("agent_fox.workspace.harvest.post_harvest_integrate", AsyncMock()),
        ):
            await pipeline.process_issue(issue, issue_body="Something is broken.")

        # Issue IS closed — reviewer confirmed PASS and fix is already on develop
        mock_platform.close_issue.assert_awaited_once()
        # Close message should mention fix already present
        close_msg = str(mock_platform.close_issue.call_args)
        assert "already present" in close_msg.lower()

    @pytest.mark.asyncio
    async def test_issue_not_closed_on_session_failure(self) -> None:
        """When a session raises, the issue is NOT closed."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.protocol import IssueResult

        config = MagicMock()
        mock_platform = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
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
        """When issue body is empty, a comment requesting detail is posted with run_id."""
        import re
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.protocol import IssueResult

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
        # AC-4: empty body comment must also include run_id
        run_id = pipeline._run_id
        assert any(f"(run: `{run_id}`)" in c for c in comments), (
            f"Expected run_id {run_id!r} in empty-body comment, got: {comments}"
        )
        # AC-5: run_id format must match YYYYMMDD_HHMMSS_<6hex>
        assert re.fullmatch(r"\d{8}_\d{6}_[0-9a-f]{6}", run_id), (
            f"run_id {run_id!r} does not match expected format"
        )


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
        from agent_fox.platform.protocol import IssueResult

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
        from agent_fox.platform.protocol import IssueResult

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


# ---------------------------------------------------------------------------
# Reviewer retry on parse failure (fixes #294)
# ---------------------------------------------------------------------------


class TestReviewerRetryOnParseFailure:
    """Verify the pipeline retries the reviewer when output is unparseable."""

    @pytest.mark.asyncio
    async def test_reviewer_retried_on_parse_failure_then_passes(self) -> None:
        """When first reviewer output is unparseable but retry produces valid
        JSON with PASS, the pipeline should succeed without coder retry."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.protocol import IssueResult

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3
        mock_platform = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        triage_response = json.dumps(
            {
                "summary": "s",
                "affected_files": [],
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "d", "preconditions": "p", "expected": "e", "assertion": "a"},
                ],
            }
        )
        pass_review_response = json.dumps(
            {
                "verdicts": [{"criterion_id": "AC-1", "verdict": "PASS", "evidence": "ok"}],
                "overall_verdict": "PASS",
                "summary": "ok",
            }
        )

        call_count = 0

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            nonlocal call_count
            outcome = MagicMock(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
            if archetype == "maintainer":
                outcome.response = triage_response
            elif archetype == "reviewer":
                call_count += 1
                if call_count == 1:
                    # First reviewer call: unparseable
                    outcome.response = "Here are my thoughts on the fix..."
                else:
                    # Retry: valid JSON
                    outcome.response = pass_review_response
            else:
                outcome.response = ""
            return outcome

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        issue = IssueResult(
            number=42,
            title="Fix something",
            html_url="https://github.com/test/repo/issues/42",
        )

        with patch.object(pipeline, "_harvest_and_push", AsyncMock(return_value="merged")):
            await pipeline.process_issue(issue, issue_body="Something is broken.")

        # Reviewer was called twice (original + retry), and the fix passed
        assert call_count == 2
        mock_platform.close_issue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reviewer_parse_failure_both_times_triggers_coder_retry(self) -> None:
        """When both reviewer attempts produce unparseable output, the pipeline
        should fall through to coder retry (escalation ladder)."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.protocol import IssueResult

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 0  # No coder retries — exhaust immediately
        mock_platform = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        triage_response = json.dumps(
            {
                "summary": "s",
                "affected_files": [],
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "d", "preconditions": "p", "expected": "e", "assertion": "a"},
                ],
            }
        )

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            outcome = MagicMock(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
            if archetype == "maintainer":
                outcome.response = triage_response
            elif archetype == "reviewer":
                # Always unparseable
                outcome.response = "I looked at the code and everything seems fine."
            else:
                outcome.response = ""
            return outcome

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        issue = IssueResult(
            number=43,
            title="Fix another thing",
            html_url="https://github.com/test/repo/issues/43",
        )

        with patch.object(pipeline, "_harvest_and_push", AsyncMock(return_value="error")):
            await pipeline.process_issue(issue, issue_body="Another thing is broken.")

        # Issue should NOT be closed (max_retries=0 exhausted)
        mock_platform.close_issue.assert_not_awaited()


# ---------------------------------------------------------------------------
# Issue #467: fix pipeline must populate session_outcomes and runs tables
# ---------------------------------------------------------------------------


class TestFixPipelineDbTelemetry:
    """Fix pipeline writes to session_outcomes and runs tables (issue #467).

    The fix pipeline previously only wrote to audit_events.  After the fix,
    every session must produce a row in session_outcomes and the runs table
    must be created/completed for each pipeline invocation.
    """

    @pytest.mark.asyncio
    async def test_session_outcomes_written_for_each_session(self) -> None:
        """record_session is called for triage, coder, and reviewer sessions."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.protocol import IssueResult

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3
        mock_platform = AsyncMock()

        # Provide a mock DuckDB connection
        mock_conn = MagicMock()

        pipeline = FixPipeline(config=config, platform=mock_platform, conn=mock_conn)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        triage_response = json.dumps(
            {
                "summary": "s",
                "affected_files": [],
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "d", "preconditions": "p", "expected": "e", "assertion": "a"},
                ],
            }
        )
        review_response = json.dumps(
            {
                "verdicts": [{"criterion_id": "AC-1", "verdict": "PASS", "evidence": "ok"}],
                "overall_verdict": "PASS",
                "summary": "ok",
            }
        )

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            outcome = MagicMock()
            outcome.status = "completed"
            outcome.input_tokens = 10
            outcome.output_tokens = 5
            outcome.cache_read_input_tokens = 0
            outcome.cache_creation_input_tokens = 0
            outcome.duration_ms = 1000
            outcome.error_message = None
            outcome.is_transport_error = False
            if archetype == "maintainer":
                outcome.response = triage_response
            elif archetype == "reviewer":
                outcome.response = review_response
            else:
                outcome.response = ""
            return outcome

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        issue = IssueResult(
            number=467,
            title="Fix broken telemetry",
            html_url="https://github.com/test/repo/issues/467",
        )

        with (
            patch("agent_fox.engine.state.record_session") as mock_record_session,
            patch("agent_fox.engine.state.update_run_totals") as mock_update_run_totals,
            patch("agent_fox.engine.state.create_run") as mock_create_run,
            patch("agent_fox.engine.state.complete_run") as mock_complete_run,
            patch.object(pipeline, "_harvest_and_push", AsyncMock(return_value="merged")),
        ):
            await pipeline.process_issue(issue, issue_body="The telemetry is broken.")

        # create_run called once at the start
        mock_create_run.assert_called_once()
        run_id_arg = mock_create_run.call_args[0][1]
        assert run_id_arg == pipeline._run_id

        # record_session called for triage (maintainer), coder, reviewer
        assert mock_record_session.call_count >= 3, (
            f"Expected at least 3 record_session calls (triage+coder+reviewer), "
            f"got {mock_record_session.call_count}"
        )

        # update_run_totals called after each session
        assert mock_update_run_totals.call_count >= 3

        # complete_run called exactly once at the end
        mock_complete_run.assert_called_once()
        completed_run_id = mock_complete_run.call_args[0][1]
        assert completed_run_id == pipeline._run_id

    @pytest.mark.asyncio
    async def test_runs_row_created_even_on_empty_body(self) -> None:
        """create_run is called even when the issue body is empty."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.protocol import IssueResult

        config = MagicMock()
        mock_platform = AsyncMock()
        mock_conn = MagicMock()

        pipeline = FixPipeline(config=config, platform=mock_platform, conn=mock_conn)

        issue = IssueResult(
            number=467,
            title="Fix something",
            html_url="https://github.com/test/repo/issues/467",
        )

        with (
            patch("agent_fox.engine.state.create_run") as mock_create_run,
            patch("agent_fox.engine.state.complete_run") as mock_complete_run,
        ):
            await pipeline.process_issue(issue, issue_body="")

        mock_create_run.assert_called_once()
        mock_complete_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_outcome_has_run_id_and_archetype(self) -> None:
        """SessionOutcomeRecord written with correct run_id and archetype."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.engine.state import SessionOutcomeRecord
        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.protocol import IssueResult

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3
        mock_platform = AsyncMock()
        mock_conn = MagicMock()

        pipeline = FixPipeline(config=config, platform=mock_platform, conn=mock_conn)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        review_response = json.dumps(
            {
                "verdicts": [{"criterion_id": "AC-1", "verdict": "PASS", "evidence": "ok"}],
                "overall_verdict": "PASS",
                "summary": "ok",
            }
        )
        triage_response = json.dumps(
            {
                "summary": "s",
                "affected_files": [],
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "d", "preconditions": "p", "expected": "e", "assertion": "a"},
                ],
            }
        )

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            outcome = MagicMock()
            outcome.status = "completed"
            outcome.input_tokens = 10
            outcome.output_tokens = 5
            outcome.cache_read_input_tokens = 0
            outcome.cache_creation_input_tokens = 0
            outcome.duration_ms = 500
            outcome.error_message = None
            outcome.is_transport_error = False
            if archetype == "maintainer":
                outcome.response = triage_response
            elif archetype == "reviewer":
                outcome.response = review_response
            else:
                outcome.response = ""
            return outcome

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        issue = IssueResult(
            number=467,
            title="Fix telemetry",
            html_url="https://github.com/test/repo/issues/467",
        )

        recorded: list[SessionOutcomeRecord] = []

        def capture_record_session(conn: object, record: SessionOutcomeRecord) -> None:
            recorded.append(record)

        with (
            patch("agent_fox.engine.state.record_session", side_effect=capture_record_session),
            patch("agent_fox.engine.state.update_run_totals"),
            patch("agent_fox.engine.state.create_run"),
            patch("agent_fox.engine.state.complete_run"),
            patch.object(pipeline, "_harvest_and_push", AsyncMock(return_value="merged")),
        ):
            await pipeline.process_issue(issue, issue_body="Telemetry is broken.")

        # All records must have the same run_id as the pipeline
        expected_run_id = pipeline._run_id
        for rec in recorded:
            assert rec.run_id == expected_run_id, f"Record run_id mismatch: {rec.run_id!r} != {expected_run_id!r}"

        # Archetypes must include maintainer (triage), coder, reviewer
        archetypes_recorded = {rec.archetype for rec in recorded}
        assert "maintainer" in archetypes_recorded, f"triage (maintainer) not in {archetypes_recorded}"
        assert "coder" in archetypes_recorded, f"coder not in {archetypes_recorded}"
        assert "reviewer" in archetypes_recorded, f"reviewer not in {archetypes_recorded}"

    @pytest.mark.asyncio
    async def test_no_db_writes_when_conn_is_none(self) -> None:
        """When conn=None, no DB functions are called (no-op path)."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.protocol import IssueResult

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3
        mock_platform = AsyncMock()

        # conn=None (default)
        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        review_response = json.dumps(
            {
                "verdicts": [{"criterion_id": "AC-1", "verdict": "PASS", "evidence": "ok"}],
                "overall_verdict": "PASS",
                "summary": "ok",
            }
        )
        triage_response = json.dumps(
            {
                "summary": "s",
                "affected_files": [],
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "d", "preconditions": "p", "expected": "e", "assertion": "a"},
                ],
            }
        )

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            outcome = MagicMock()
            outcome.status = "completed"
            outcome.input_tokens = 10
            outcome.output_tokens = 5
            outcome.cache_read_input_tokens = 0
            outcome.cache_creation_input_tokens = 0
            outcome.duration_ms = 500
            outcome.error_message = None
            outcome.is_transport_error = False
            if archetype == "maintainer":
                outcome.response = triage_response
            elif archetype == "reviewer":
                outcome.response = review_response
            else:
                outcome.response = ""
            return outcome

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        issue = IssueResult(
            number=467,
            title="Fix telemetry",
            html_url="https://github.com/test/repo/issues/467",
        )

        with (
            patch("agent_fox.engine.state.record_session") as mock_record_session,
            patch("agent_fox.engine.state.create_run") as mock_create_run,
            patch("agent_fox.engine.state.complete_run") as mock_complete_run,
            patch.object(pipeline, "_harvest_and_push", AsyncMock(return_value="merged")),
        ):
            await pipeline.process_issue(issue, issue_body="Telemetry is broken.")

        # None of the DB functions should have been called
        mock_record_session.assert_not_called()
        mock_create_run.assert_not_called()
        mock_complete_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_engine_passes_conn_to_fix_pipeline(self) -> None:
        """NightShiftEngine passes self._conn to FixPipeline."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.engine import NightShiftEngine
        from agent_fox.platform.protocol import IssueResult

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None
        config.night_shift.push_fix_branch = False

        mock_platform = AsyncMock()
        mock_conn = MagicMock()

        engine = NightShiftEngine(config=config, platform=mock_platform, conn=mock_conn)

        issue = IssueResult(
            number=467,
            title="Fix something",
            html_url="https://github.com/test/repo/issues/467",
            body="The issue body",
        )

        captured_pipelines: list[object] = []

        original_fix_pipeline = __import__(
            "agent_fox.nightshift.fix_pipeline", fromlist=["FixPipeline"]
        ).FixPipeline

        class CapturingFixPipeline(original_fix_pipeline):  # type: ignore[misc]
            def __init__(self, *args: object, **kwargs: object) -> None:
                captured_pipelines.append(kwargs.get("conn"))
                super().__init__(*args, **kwargs)

            async def process_issue(self, *args: object, **kwargs: object) -> object:  # type: ignore[override]
                return MagicMock(sessions_run=0)

        with patch(
            "agent_fox.nightshift.engine.FixPipeline",
            CapturingFixPipeline,
        ):
            await engine._process_fix(issue)

        assert len(captured_pipelines) == 1
        assert captured_pipelines[0] is mock_conn, (
            f"Expected conn={mock_conn!r} to be passed, got {captured_pipelines[0]!r}"
        )
