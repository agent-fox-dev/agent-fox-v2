"""Property-based tests for fix branch push to upstream feature.

Test Spec: TS-93-P1 through TS-93-P5
Properties: 1-5 from design.md (spec 93)
Requirements: 93-REQ-2.1, 93-REQ-2.2, 93-REQ-3.1, 93-REQ-3.2, 93-REQ-3.3,
              93-REQ-3.E1, 93-REQ-3.E2
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.nightshift.fix_pipeline import FixPipeline
from agent_fox.platform.protocol import IssueResult
from agent_fox.workspace import WorkspaceInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_workspace(branch: str = "fix/1-test-issue") -> WorkspaceInfo:
    return WorkspaceInfo(
        path=Path("/tmp/mock-worktree"),
        branch=branch,
        spec_name="fix-issue-1",
        task_group=0,
    )


def _make_issue(number: int = 1, title: str = "test") -> IssueResult:
    return IssueResult(
        number=number,
        title=title,
        html_url=f"https://github.com/test/repo/issues/{number}",
    )


def _make_pipeline(*, push_fix_branch: bool) -> FixPipeline:
    """Create a FixPipeline with mocked dependencies."""

    config = MagicMock()
    config.night_shift.push_fix_branch = push_fix_branch
    config.orchestrator.retries_before_escalation = 1
    config.orchestrator.max_retries = 1

    mock_platform = AsyncMock()
    mock_platform.add_issue_comment = AsyncMock()
    mock_platform.close_issue = AsyncMock()
    mock_platform.remove_label = AsyncMock()

    pipeline = FixPipeline(config=config, platform=mock_platform)
    pipeline._setup_workspace = AsyncMock(  # type: ignore[method-assign]
        return_value=_mock_workspace()
    )
    pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
    pipeline._harvest_and_push = AsyncMock(return_value="merged")  # type: ignore[method-assign]
    pipeline._coder_review_loop = AsyncMock(return_value=True)  # type: ignore[method-assign]
    pipeline._run_triage = AsyncMock(  # type: ignore[method-assign]
        return_value=MagicMock(criteria=[], summary="ok")
    )
    return pipeline


# ---------------------------------------------------------------------------
# TS-93-P1: Push Gating Invariant
# Property 1: When push_fix_branch=False, _push_fix_branch_upstream is never called.
# Requirement: 93-REQ-3.3
# ---------------------------------------------------------------------------


class TestPushGatingInvariant:
    """When push disabled, _push_fix_branch_upstream must never be invoked."""

    @pytest.mark.asyncio
    @given(
        issue_number=st.integers(min_value=1, max_value=99999),
        title=st.text(min_size=0, max_size=50),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_push_gating(self, issue_number: int, title: str) -> None:
        """For any config with push_fix_branch=False, push is never invoked."""
        pipeline = _make_pipeline(push_fix_branch=False)

        push_upstream = AsyncMock(return_value=True)
        pipeline._push_fix_branch_upstream = push_upstream  # type: ignore[method-assign]

        issue = _make_issue(number=issue_number, title=title or "test")
        await pipeline.process_issue(issue, issue_body="fix body")

        push_upstream.assert_not_called()


# ---------------------------------------------------------------------------
# TS-93-P2: Branch Name Always Contains Issue Number
# Property 2: sanitise_branch_name(title, issue_number) always contains str(issue_number).
# Requirements: 93-REQ-2.1, 93-REQ-2.2
# ---------------------------------------------------------------------------


class TestBranchNameContainsIssueNumber:
    """Branch name invariant: always contains the issue number."""

    @given(
        issue_number=st.integers(min_value=1, max_value=999999),
        title=st.text(max_size=100),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_branch_name_contains_number(self, issue_number: int, title: str) -> None:
        """str(issue_number) is always a substring of sanitise_branch_name(title, issue_number)."""
        from agent_fox.nightshift.spec_builder import sanitise_branch_name

        result = sanitise_branch_name(title, issue_number)
        assert str(issue_number) in result, f"Issue number {issue_number} not found in branch name '{result}'"
        assert result.startswith("fix/"), f"Branch name '{result}' does not start with 'fix/'"


# ---------------------------------------------------------------------------
# TS-93-P3: Push Before Harvest Ordering
# Property 3: When push enabled and loop passes, push always precedes harvest.
# Requirement: 93-REQ-3.1
# ---------------------------------------------------------------------------


class TestPushBeforeHarvestOrdering:
    """Push must always precede harvest in the call sequence."""

    @pytest.mark.asyncio
    @given(
        issue_number=st.integers(min_value=1, max_value=99999),
        title=st.text(min_size=1, max_size=50),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_push_before_harvest(self, issue_number: int, title: str) -> None:
        """For any issue, push index < harvest index in call sequence."""
        pipeline = _make_pipeline(push_fix_branch=True)

        call_order: list[str] = []

        original_harvest = pipeline._harvest_and_push

        async def tracking_harvest(*args: Any, **kwargs: Any) -> str:
            call_order.append("harvest")
            return await original_harvest(*args, **kwargs)

        pipeline._harvest_and_push = tracking_harvest  # type: ignore[method-assign]

        async def push_side_effect(*a: object, **k: object) -> bool:
            call_order.append("push")
            return True

        push_upstream = AsyncMock(side_effect=push_side_effect)
        pipeline._push_fix_branch_upstream = push_upstream  # type: ignore[method-assign]

        issue = _make_issue(number=issue_number, title=title)
        await pipeline.process_issue(issue, issue_body="fix body")

        assert "push" in call_order, "push was not called"
        assert "harvest" in call_order, "harvest was not called"
        push_idx = call_order.index("push")
        harvest_idx = call_order.index("harvest")
        assert push_idx < harvest_idx, f"Expected push before harvest, got order: {call_order}"


# ---------------------------------------------------------------------------
# TS-93-P4: Push Failure Resilience
# Property 4: When push raises any exception, harvest still runs and no exception propagates.
# Requirements: 93-REQ-3.E1, 93-REQ-3.E2
# ---------------------------------------------------------------------------


class TestPushFailureResilience:
    """When push raises any exception, harvest still executes."""

    @pytest.mark.asyncio
    @given(
        exc_type=st.sampled_from([RuntimeError, OSError, TimeoutError, ConnectionError]),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_push_failure_resilience(self, exc_type: type[Exception]) -> None:
        """For any exception from push, harvest still executes and process_issue does not raise."""
        pipeline = _make_pipeline(push_fix_branch=True)

        mock_harvest = AsyncMock(return_value="merged")
        pipeline._harvest_and_push = mock_harvest  # type: ignore[method-assign]

        with patch(
            "agent_fox.workspace.git.push_to_remote",
            new_callable=AsyncMock,
            side_effect=exc_type("fail"),
        ):
            # Must not raise
            await pipeline.process_issue(_make_issue(), issue_body="fix body")

        mock_harvest.assert_awaited_once()


# ---------------------------------------------------------------------------
# TS-93-P5: Force Push Semantics
# Property 5: Every call to push_to_remote for a fix branch uses force=True.
# Requirement: 93-REQ-3.2
# ---------------------------------------------------------------------------


class TestForcePushSemantics:
    """Every fix branch push uses force=True."""

    @pytest.mark.asyncio
    @given(
        issue_number=st.integers(min_value=1, max_value=99999),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_force_push_semantics(self, issue_number: int) -> None:
        """push_to_remote is always called with force=True for fix branches."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.nightshift.spec_builder import InMemorySpec

        config = MagicMock()
        config.night_shift.push_fix_branch = True
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 1

        mock_platform = AsyncMock()
        pipeline = FixPipeline(config=config, platform=mock_platform)

        branch_name = f"fix/{issue_number}-test"
        spec = InMemorySpec(
            issue_number=issue_number,
            title="test",
            task_prompt="Fix this",
            system_context="context",
            branch_name=branch_name,
        )
        workspace = _mock_workspace(branch_name)

        with patch("agent_fox.workspace.git.push_to_remote", new_callable=AsyncMock) as mock_push:
            mock_push.return_value = True
            await pipeline._push_fix_branch_upstream(spec, workspace)

        mock_push.assert_awaited_once()
        call = mock_push.call_args
        force_value = call.kwargs.get("force") if call.kwargs else None
        if force_value is None and call.args and len(call.args) > 2:
            force_value = call.args[2]
        assert force_value is True, f"Expected push_to_remote to be called with force=True, got force={force_value}"
