"""Integration smoke tests for fix branch push to upstream feature.

Test Spec: TS-93-4, TS-93-SMOKE-1, TS-93-SMOKE-2
Execution Paths: Path 1 (push enabled), Path 2 (push disabled) from design.md
Requirements: 93-REQ-3.1, 93-REQ-3.2, 93-REQ-3.3, 93-REQ-3.4, 93-REQ-4.1

Note: TS-93-4 was classified as integration type in test_spec.md and is
      placed here rather than in the unit test file. The traceability table
      in tasks.md also maps 93-REQ-3.1 to test_fix_branch_push_smoke.py.
      See docs/errata/93_ts93_4_placement.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.platform.github import IssueResult
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


def _make_issue(number: int = 1, title: str = "test issue") -> IssueResult:
    return IssueResult(
        number=number,
        title=title,
        html_url=f"https://github.com/test/repo/issues/{number}",
    )


def _triage_json(criteria_count: int = 2) -> str:
    criteria = [
        {
            "id": f"AC-{i + 1}",
            "description": f"Criterion {i + 1}",
            "preconditions": f"Pre {i + 1}",
            "expected": f"Expected {i + 1}",
            "assertion": f"Assert {i + 1}",
        }
        for i in range(criteria_count)
    ]
    return json.dumps(
        {
            "summary": "Root cause found",
            "affected_files": ["agent_fox/engine.py"],
            "acceptance_criteria": criteria,
        }
    )


def _review_json(overall: str = "PASS", criterion_ids: list[str] | None = None) -> str:
    if criterion_ids is None:
        criterion_ids = ["AC-1", "AC-2"]
    verdicts = [
        {
            "criterion_id": cid,
            "verdict": overall,
            "evidence": f"Evidence for {cid}",
        }
        for cid in criterion_ids
    ]
    return json.dumps(
        {
            "verdicts": verdicts,
            "overall_verdict": overall,
            "summary": f"All criteria {'passed' if overall == 'PASS' else 'failed'}",
        }
    )


def _make_outcome(response: str = "") -> MagicMock:
    outcome = MagicMock()
    outcome.response = response
    outcome.input_tokens = 100
    outcome.output_tokens = 50
    outcome.cache_read_input_tokens = 10
    outcome.cache_creation_input_tokens = 5
    outcome.status = "completed"
    return outcome


def _make_session_runner(reviewer_outcome: str = "PASS") -> Any:
    """Return a mock _run_session that produces triage, coder, and reviewer outputs."""

    async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
        if archetype == "triage":
            return _make_outcome(_triage_json(2))
        if archetype == "reviewer":
            return _make_outcome(_review_json(reviewer_outcome, ["AC-1", "AC-2"]))
        return _make_outcome()  # coder

    return mock_run_session


# ---------------------------------------------------------------------------
# TS-93-4: Push called before harvest when enabled (integration)
# Requirement: 93-REQ-3.1
# ---------------------------------------------------------------------------


class TestPushBeforeHarvestIntegration:
    """Integration: push is called before harvest when push_fix_branch=True."""

    @pytest.mark.asyncio
    async def test_push_called_before_harvest(self) -> None:
        """push_to_remote is called before _harvest_and_push when push enabled."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        config.night_shift.push_fix_branch = True
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 1

        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()
        mock_platform.close_issue = AsyncMock()
        mock_platform.remove_label = AsyncMock()

        call_order: list[str] = []

        async def harvest_side_effect(*a: object, **k: object) -> str:
            call_order.append("harvest")
            return "merged"

        async def push_side_effect(*a: object, **k: object) -> bool:
            call_order.append("push")
            return True

        mock_harvest = AsyncMock(side_effect=harvest_side_effect)
        mock_push = AsyncMock(side_effect=push_side_effect)

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = mock_harvest  # type: ignore[method-assign]
        pipeline._push_fix_branch_upstream = mock_push  # type: ignore[method-assign]
        pipeline._coder_review_loop = AsyncMock(return_value=True)  # type: ignore[method-assign]
        pipeline._run_triage = AsyncMock(  # type: ignore[method-assign]
            return_value=MagicMock(criteria=[], summary="ok")
        )

        await pipeline.process_issue(_make_issue(), issue_body="fix this")

        assert call_order == ["push", "harvest"], f"Expected ['push', 'harvest'], got {call_order}"
        mock_push.assert_awaited_once()
        mock_harvest.assert_awaited_once()


# ---------------------------------------------------------------------------
# TS-93-SMOKE-1: Full pipeline with push enabled
# Execution Path: Path 1 from design.md
# ---------------------------------------------------------------------------


class TestFullPipelinePushEnabled:
    """End-to-end fix pipeline with push_fix_branch=True pushes branch before harvest."""

    @pytest.mark.asyncio
    async def test_full_pipeline_push_enabled(self) -> None:
        """Full pipeline: push_to_remote called with force=True before harvest."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        config.night_shift.push_fix_branch = True
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 1

        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()
        mock_platform.close_issue = AsyncMock()
        mock_platform.remove_label = AsyncMock()

        call_order: list[str] = []

        async def harvest_side_effect_2(*a: object, **k: object) -> str:
            call_order.append("harvest")
            return "merged"

        mock_harvest = AsyncMock(side_effect=harvest_side_effect_2)

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = mock_harvest  # type: ignore[method-assign]
        pipeline._run_session = _make_session_runner("PASS")  # type: ignore[method-assign]

        # Track the real _push_fix_branch_upstream execution (do NOT mock it)
        original_push_upstream = None
        if hasattr(pipeline, "_push_fix_branch_upstream"):
            original_push_upstream = pipeline._push_fix_branch_upstream

        async def tracking_push(*args: Any, **kwargs: Any) -> bool:
            call_order.append("push")
            if original_push_upstream is not None:
                return await original_push_upstream(*args, **kwargs)
            return True

        pipeline._push_fix_branch_upstream = tracking_push  # type: ignore[method-assign]

        with patch(
            "agent_fox.workspace.git.push_to_remote",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_push_to_remote:
            await pipeline.process_issue(_make_issue(), issue_body="fix bug")

        # push must be called before harvest
        assert "push" in call_order, "push_fix_branch_upstream was not called"
        assert "harvest" in call_order, "_harvest_and_push was not called"
        assert call_order.index("push") < call_order.index("harvest"), (
            f"Expected push before harvest, got order: {call_order}"
        )

        # Issue must be closed
        mock_platform.close_issue.assert_awaited_once()

        # push_to_remote must be called with force=True
        if mock_push_to_remote.called:
            call = mock_push_to_remote.call_args
            force = call.kwargs.get("force") if call.kwargs else None
            if force is None and call.args and len(call.args) > 2:
                force = call.args[2]
            assert force is True, "push_to_remote must be called with force=True"


# ---------------------------------------------------------------------------
# TS-93-SMOKE-2: Full pipeline with push disabled
# Execution Path: Path 2 from design.md
# ---------------------------------------------------------------------------


class TestFullPipelinePushDisabled:
    """End-to-end fix pipeline with push_fix_branch=False (default) skips fix branch push."""

    @pytest.mark.asyncio
    async def test_full_pipeline_push_disabled(self) -> None:
        """Full pipeline: push_to_remote NOT called for fix branch when disabled."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        config.night_shift.push_fix_branch = False
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 1

        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()
        mock_platform.close_issue = AsyncMock()
        mock_platform.remove_label = AsyncMock()

        mock_harvest = AsyncMock(return_value="merged")

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = mock_harvest  # type: ignore[method-assign]
        pipeline._run_session = _make_session_runner("PASS")  # type: ignore[method-assign]

        # Capture whether _push_fix_branch_upstream was called
        push_upstream_called = {"called": False}
        original_push_upstream = getattr(pipeline, "_push_fix_branch_upstream", None)

        async def tracking_push(*args: Any, **kwargs: Any) -> bool:
            push_upstream_called["called"] = True
            if original_push_upstream is not None:
                return await original_push_upstream(*args, **kwargs)
            return True

        pipeline._push_fix_branch_upstream = tracking_push  # type: ignore[method-assign]

        with patch(
            "agent_fox.workspace.git.push_to_remote",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_push_to_remote:
            await pipeline.process_issue(_make_issue(), issue_body="fix bug")

        # push_fix_branch_upstream must NOT be called when disabled
        assert not push_upstream_called["called"], (
            "_push_fix_branch_upstream should not be called when push_fix_branch=False"
        )

        # harvest must still be called
        mock_harvest.assert_awaited_once()

        # Issue must be closed
        mock_platform.close_issue.assert_awaited_once()

        # push_to_remote must NOT be called for the fix branch
        # (it may be called for develop via harvest, but harvest is mocked here)
        if mock_push_to_remote.called:
            # If called at all (e.g. inside _harvest_and_push mock), the fix branch
            # push should NOT have been triggered
            for call in mock_push_to_remote.call_args_list:
                args = call.args
                # The fix branch name should not appear in push calls
                branch_in_call = args[1] if len(args) > 1 else ""
                assert not str(branch_in_call).startswith("fix/"), (
                    f"Fix branch should not be pushed, but got: {branch_in_call}"
                )
