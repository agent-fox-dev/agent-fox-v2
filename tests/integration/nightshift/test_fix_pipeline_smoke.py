"""Integration smoke tests for the fix pipeline triage/reviewer flow.

Test Spec: TS-82-SMOKE-1, TS-82-SMOKE-2, TS-82-SMOKE-3
Requirements: 82-REQ-7.1, 82-REQ-8.2, 82-REQ-8.3, 82-REQ-7.E1
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_fox.platform.protocol import IssueResult
from agent_fox.workspace import WorkspaceInfo


def _mock_workspace() -> WorkspaceInfo:
    return WorkspaceInfo(
        path=Path("/tmp/mock-worktree"),
        branch="fix/test-branch",
        spec_name="fix-issue-42",
        task_group=0,
    )


def _make_issue(number: int = 42) -> IssueResult:
    return IssueResult(
        number=number,
        title="Fix the bug",
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


def _review_json(
    overall: str = "PASS",
    criterion_ids: list[str] | None = None,
) -> str:
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


# ---------------------------------------------------------------------------
# TS-82-SMOKE-1: Full pipeline happy path
# Execution Paths: 1, 2, 3
# ---------------------------------------------------------------------------


class TestFullPipelineHappyPath:
    """End-to-end pipeline with triage, coder, and reviewer all succeeding."""

    @pytest.mark.asyncio
    async def test_happy_path_all_pass(self) -> None:
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()
        mock_platform.close_issue = AsyncMock()

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = AsyncMock(return_value="merged")  # type: ignore[method-assign]

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            if archetype == "maintainer":
                return _make_outcome(_triage_json(2))
            if archetype == "reviewer":
                return _make_outcome(_review_json("PASS", ["AC-1", "AC-2"]))
            return _make_outcome()  # coder

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        metrics = await pipeline.process_issue(_make_issue(), issue_body="bug description")

        # Verify comment posting (real parsing, not mocked)
        assert mock_platform.add_issue_comment.call_count >= 3

        # Verify triage comment contains criteria
        comments = [str(call) for call in mock_platform.add_issue_comment.call_args_list]
        assert any("AC-1" in c and "AC-2" in c for c in comments)

        # Verify review comment contains PASS
        assert any("PASS" in c for c in comments)

        # Issue is closed
        mock_platform.close_issue.assert_awaited_once()

        # 3 sessions: triage + coder + reviewer
        assert metrics.sessions_run == 3


# ---------------------------------------------------------------------------
# TS-82-SMOKE-2: Retry loop with escalation
# Execution Path: 4
# ---------------------------------------------------------------------------


class TestRetryLoopWithEscalation:
    """Pipeline where reviewer FAILs twice, escalation occurs, third passes."""

    @pytest.mark.asyncio
    async def test_retry_with_escalation(self) -> None:
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()
        mock_platform.close_issue = AsyncMock()

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = AsyncMock(return_value="merged")  # type: ignore[method-assign]

        reviewer_call_count = {"n": 0}
        model_ids_used: list[str | None] = []

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            if archetype == "maintainer":
                return _make_outcome(_triage_json(2))
            if archetype == "reviewer":
                reviewer_call_count["n"] += 1
                if reviewer_call_count["n"] < 3:
                    return _make_outcome(_review_json("FAIL", ["AC-1", "AC-2"]))
                return _make_outcome(_review_json("PASS", ["AC-1", "AC-2"]))
            return _make_outcome()

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        # Capture model IDs
        original_run_coder = pipeline._run_coder_session

        async def capturing_coder(
            workspace: object,
            spec: object,
            system_prompt: str,
            task_prompt: str,
            model_id: str | None = None,
        ) -> MagicMock:
            model_ids_used.append(model_id)
            return await original_run_coder(workspace, spec, system_prompt, task_prompt, model_id)  # type: ignore[return-value, arg-type]

        pipeline._run_coder_session = capturing_coder  # type: ignore[assignment]

        metrics = await pipeline.process_issue(_make_issue(), issue_body="hard bug")

        # 1 triage + 3 coder + 3 reviewer = 7 sessions
        assert metrics.sessions_run == 7

        # Model tier should change (escalation occurred)
        assert model_ids_used[0] != model_ids_used[2]

        # Issue is closed on final PASS
        mock_platform.close_issue.assert_awaited_once()


# ---------------------------------------------------------------------------
# TS-82-SMOKE-3: Triage failure with graceful fallback
# Execution Paths: 2, 3 (Path 1 failing)
# ---------------------------------------------------------------------------


class TestTriageFailureFallback:
    """Pipeline continues when triage session fails, using issue body only."""

    @pytest.mark.asyncio
    async def test_triage_failure_coder_proceeds(self) -> None:
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()
        mock_platform.close_issue = AsyncMock()

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = AsyncMock(return_value="merged")  # type: ignore[method-assign]

        triage_attempted = {"value": False}

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            if archetype == "maintainer":
                triage_attempted["value"] = True
                raise Exception("backend error")
            if archetype == "reviewer":
                # With no criteria, reviewer verifies from issue text
                return _make_outcome(
                    json.dumps(
                        {
                            "verdicts": [],
                            "overall_verdict": "PASS",
                            "summary": "Fix looks good",
                        }
                    )
                )
            return _make_outcome()

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        metrics = await pipeline.process_issue(_make_issue(), issue_body="simple bug")

        # Triage was attempted but failed
        assert triage_attempted["value"]

        # Pipeline completed without raising
        assert metrics.sessions_run >= 2

        # Issue is closed
        mock_platform.close_issue.assert_awaited_once()
