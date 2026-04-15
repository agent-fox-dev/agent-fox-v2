"""Tests for fix pipeline triage/reviewer wiring, comments, retry, escalation.

Test Spec: TS-82-10 through TS-82-20
Requirements: 82-REQ-3.1, 82-REQ-3.E1, 82-REQ-5.E1, 82-REQ-6.1, 82-REQ-6.E1,
              82-REQ-7.1, 82-REQ-7.2, 82-REQ-7.3, 82-REQ-7.E1,
              82-REQ-8.1, 82-REQ-8.2, 82-REQ-8.3, 82-REQ-8.4, 82-REQ-8.E1
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


def _triage_json(criteria_count: int = 1) -> str:
    """Build valid triage JSON with N criteria."""
    criteria = [
        {
            "id": f"AC-{i + 1}",
            "description": f"Criterion {i + 1} description",
            "preconditions": f"Precondition {i + 1}",
            "expected": f"Expected {i + 1}",
            "assertion": f"Assertion {i + 1}",
        }
        for i in range(criteria_count)
    ]
    return json.dumps(
        {
            "summary": "Root cause analysis",
            "affected_files": ["agent_fox/engine.py"],
            "acceptance_criteria": criteria,
        }
    )


def _review_json(
    overall: str = "PASS",
    criterion_ids: list[str] | None = None,
    verdicts: list[str] | None = None,
) -> str:
    """Build valid reviewer JSON."""
    if criterion_ids is None:
        criterion_ids = ["AC-1"]
    if verdicts is None:
        verdicts = [overall] * len(criterion_ids)
    verdict_objs = [
        {
            "criterion_id": cid,
            "verdict": v,
            "evidence": f"Evidence for {cid}: {'ok' if v == 'PASS' else 'Function returns wrong value'}",
        }
        for cid, v in zip(criterion_ids, verdicts)
    ]
    return json.dumps(
        {
            "verdicts": verdict_objs,
            "overall_verdict": overall,
            "summary": "Review summary",
        }
    )


def _make_session_outcome(response: str = "") -> MagicMock:
    """Create a mock SessionOutcome with token fields."""
    outcome = MagicMock()
    outcome.response = response
    outcome.input_tokens = 100
    outcome.output_tokens = 50
    outcome.cache_read_input_tokens = 10
    outcome.cache_creation_input_tokens = 5
    outcome.status = "completed"
    return outcome


def _make_pipeline(
    max_retries: int = 3,
    retries_before_escalation: int = 1,
) -> tuple:
    """Create a FixPipeline with mocked config and platform.

    Returns (pipeline, mock_platform, config).
    """
    from agent_fox.nightshift.fix_pipeline import FixPipeline

    config = MagicMock()
    config.orchestrator.retries_before_escalation = retries_before_escalation
    config.orchestrator.max_retries = max_retries

    mock_platform = AsyncMock()
    mock_platform.add_issue_comment = AsyncMock()
    mock_platform.close_issue = AsyncMock()

    pipeline = FixPipeline(config=config, platform=mock_platform)
    pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
    pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
    pipeline._harvest_and_push = AsyncMock(return_value="merged")  # type: ignore[method-assign]

    return pipeline, mock_platform, config


# ---------------------------------------------------------------------------
# TS-82-10: Pipeline runs triage-coder-reviewer sequence
# Requirement: 82-REQ-7.1
# ---------------------------------------------------------------------------


class TestPipelineArchetypeSequence:
    """Verify process_issue invokes archetypes in the correct order."""

    @pytest.mark.asyncio
    async def test_triage_coder_reviewer_order(self) -> None:
        pipeline, mock_platform, _ = _make_pipeline()

        archetypes_called: list[str] = []

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            archetypes_called.append(archetype)
            if archetype == "maintainer":
                return _make_session_outcome(_triage_json(1))
            if archetype == "reviewer":
                return _make_session_outcome(_review_json("PASS", ["AC-1"]))
            return _make_session_outcome()

        pipeline._run_session = mock_run_session  # type: ignore[method-assign]

        await pipeline.process_issue(_make_issue(), issue_body="fix the bug")

        assert archetypes_called[0] == "maintainer"
        assert "coder" in archetypes_called or any("coder" in str(a) for a in archetypes_called)
        assert archetypes_called[-1] == "reviewer"


# ---------------------------------------------------------------------------
# TS-82-11: Coder prompt includes triage criteria
# Requirement: 82-REQ-7.2
# ---------------------------------------------------------------------------


class TestCoderPromptIncludesCriteria:
    """Verify coder system prompt includes triage acceptance criteria."""

    def test_coder_prompt_contains_criteria(self) -> None:
        pipeline, _, _ = _make_pipeline()

        # Build a TriageResult with two criteria
        from agent_fox.session.review_parser import parse_triage_output

        triage_result = parse_triage_output(_triage_json(2), "fix-issue-42", "s1")

        from agent_fox.nightshift.spec_builder import build_in_memory_spec

        spec = build_in_memory_spec(_make_issue(), "fix the bug")

        system_prompt, task_prompt = pipeline._build_coder_prompt(spec, triage_result)

        assert "AC-1" in system_prompt
        assert "AC-2" in system_prompt
        assert triage_result.criteria[0].description in system_prompt


# ---------------------------------------------------------------------------
# TS-82-12: Reviewer prompt includes triage criteria
# Requirements: 82-REQ-7.3, 82-REQ-5.3
# ---------------------------------------------------------------------------


class TestReviewerPromptIncludesCriteria:
    """Verify reviewer system prompt includes triage criteria."""

    def test_reviewer_prompt_contains_criteria(self) -> None:
        pipeline, _, _ = _make_pipeline()

        from agent_fox.session.review_parser import parse_triage_output

        triage_result = parse_triage_output(_triage_json(1), "fix-issue-42", "s1")

        from agent_fox.nightshift.spec_builder import build_in_memory_spec

        spec = build_in_memory_spec(_make_issue(), "fix the bug")

        system_prompt, task_prompt = pipeline._build_reviewer_prompt(spec, triage_result)

        assert "AC-1" in system_prompt
        assert triage_result.criteria[0].description in system_prompt


# ---------------------------------------------------------------------------
# TS-82-13: Triage comment posted to issue
# Requirement: 82-REQ-3.1
# ---------------------------------------------------------------------------


class TestTriageCommentPosted:
    """Verify triage report is posted as a comment."""

    @pytest.mark.asyncio
    async def test_triage_comment_contains_criteria(self) -> None:
        pipeline, mock_platform, _ = _make_pipeline()

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            if archetype == "maintainer":
                return _make_session_outcome(_triage_json(1))
            if archetype == "reviewer":
                return _make_session_outcome(_review_json("PASS", ["AC-1"]))
            return _make_session_outcome()

        pipeline._run_session = mock_run_session  # type: ignore[method-assign]

        await pipeline.process_issue(_make_issue(), issue_body="bug")

        comments = [str(call) for call in mock_platform.add_issue_comment.call_args_list]
        # At least one comment should contain the criterion ID
        assert any("AC-1" in c for c in comments)


# ---------------------------------------------------------------------------
# TS-82-14: Reviewer comment posted to issue
# Requirement: 82-REQ-6.1
# ---------------------------------------------------------------------------


class TestReviewerCommentPosted:
    """Verify review report is posted as a comment."""

    @pytest.mark.asyncio
    async def test_review_comment_contains_verdict(self) -> None:
        pipeline, mock_platform, _ = _make_pipeline()

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            if archetype == "maintainer":
                return _make_session_outcome(_triage_json(1))
            if archetype == "reviewer":
                return _make_session_outcome(_review_json("PASS", ["AC-1"]))
            return _make_session_outcome()

        pipeline._run_session = mock_run_session  # type: ignore[method-assign]

        await pipeline.process_issue(_make_issue(), issue_body="bug")

        comments = [str(call) for call in mock_platform.add_issue_comment.call_args_list]
        # At least one comment should contain verdict info
        review_comments = [c for c in comments if "PASS" in c or "verdict" in c.lower()]
        assert len(review_comments) >= 1
        assert any("AC-1" in c for c in review_comments)


# ---------------------------------------------------------------------------
# TS-82-15: Coder retried on reviewer FAIL with feedback
# Requirement: 82-REQ-8.1
# ---------------------------------------------------------------------------


class TestCoderRetryOnFail:
    """Verify reviewer FAIL triggers coder retry with evidence."""

    @pytest.mark.asyncio
    async def test_coder_retried_with_evidence(self) -> None:
        pipeline, mock_platform, _ = _make_pipeline(max_retries=3)

        call_count = {"reviewer": 0}
        coder_prompts: list[dict] = []

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            if archetype == "maintainer":
                return _make_session_outcome(_triage_json(1))
            if archetype == "reviewer":
                call_count["reviewer"] += 1
                if call_count["reviewer"] == 1:
                    return _make_session_outcome(_review_json("FAIL", ["AC-1"], ["FAIL"]))
                return _make_session_outcome(_review_json("PASS", ["AC-1"]))
            # coder
            return _make_session_outcome()

        pipeline._run_session = mock_run_session  # type: ignore[method-assign]

        # Capture coder prompts by intercepting _build_coder_prompt
        original_build = pipeline._build_coder_prompt

        def capturing_build(*args: object, **kwargs: object) -> tuple:
            result = original_build(*args, **kwargs)
            coder_prompts.append({"system": result[0], "task": result[1]})
            return result

        pipeline._build_coder_prompt = capturing_build  # type: ignore[method-assign]

        await pipeline.process_issue(_make_issue(), issue_body="bug")

        # Coder should be called at least twice
        assert len(coder_prompts) >= 2
        # Second coder prompt should contain reviewer evidence
        second_prompt = coder_prompts[1]["task"] + coder_prompts[1]["system"]
        assert "Function returns wrong value" in second_prompt


# ---------------------------------------------------------------------------
# TS-82-16: Model escalation on repeated FAIL
# Requirements: 82-REQ-8.2, 82-REQ-8.3
# ---------------------------------------------------------------------------


class TestModelEscalation:
    """Verify pipeline escalates model tier after repeated FAILs."""

    @pytest.mark.asyncio
    async def test_model_tier_changes_after_escalation(self) -> None:
        pipeline, mock_platform, _ = _make_pipeline(max_retries=3, retries_before_escalation=1)

        model_ids_used: list[str | None] = []

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            if archetype == "maintainer":
                return _make_session_outcome(_triage_json(1))
            if archetype == "reviewer":
                return _make_session_outcome(_review_json("FAIL", ["AC-1"], ["FAIL"]))
            return _make_session_outcome()

        pipeline._run_session = mock_run_session  # type: ignore[method-assign]

        # Capture model_id passed to coder sessions
        original_run_coder = pipeline._run_coder_session

        async def capturing_run_coder(
            workspace: object,
            spec: object,
            system_prompt: str,
            task_prompt: str,
            model_id: str | None = None,
        ) -> MagicMock:
            model_ids_used.append(model_id)
            return await original_run_coder(workspace, spec, system_prompt, task_prompt, model_id)

        pipeline._run_coder_session = capturing_run_coder  # type: ignore[method-assign]

        await pipeline.process_issue(_make_issue(), issue_body="hard bug")

        # At least some model_ids should differ (escalation occurred)
        assert len(model_ids_used) >= 2
        # First and last should differ (escalation happened)
        assert model_ids_used[0] != model_ids_used[-1]


# ---------------------------------------------------------------------------
# TS-82-17: Pipeline stops and posts failure on exhaustion
# Requirement: 82-REQ-8.4
# ---------------------------------------------------------------------------


class TestPipelineExhaustion:
    """Verify pipeline posts failure comment when ladder is exhausted."""

    @pytest.mark.asyncio
    async def test_exhaustion_posts_failure_no_close(self) -> None:
        pipeline, mock_platform, _ = _make_pipeline(max_retries=1, retries_before_escalation=1)

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            if archetype == "maintainer":
                return _make_session_outcome(_triage_json(1))
            if archetype == "reviewer":
                return _make_session_outcome(_review_json("FAIL", ["AC-1"], ["FAIL"]))
            return _make_session_outcome()

        pipeline._run_session = mock_run_session  # type: ignore[method-assign]

        await pipeline.process_issue(_make_issue(), issue_body="bug")

        # Check failure comment posted
        comments = [str(call) for call in mock_platform.add_issue_comment.call_args_list]
        failure_comments = [c for c in comments if "failed" in c.lower() or "exhausted" in c.lower()]
        assert len(failure_comments) >= 1

        # Issue should NOT be closed
        mock_platform.close_issue.assert_not_awaited()


# ---------------------------------------------------------------------------
# TS-82-18: Triage failure does not block pipeline
# Requirement: 82-REQ-7.E1
# ---------------------------------------------------------------------------


class TestTriageFailureFallback:
    """Verify triage failure allows coder to proceed with issue body."""

    @pytest.mark.asyncio
    async def test_triage_exception_continues_pipeline(self) -> None:
        pipeline, mock_platform, _ = _make_pipeline()

        coder_called = {"value": False}

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            if archetype == "maintainer":
                raise Exception("timeout")
            if archetype == "reviewer":
                return _make_session_outcome(_review_json("PASS", ["AC-1"]))
            coder_called["value"] = True
            return _make_session_outcome()

        pipeline._run_session = mock_run_session  # type: ignore[method-assign]

        # Should not raise
        await pipeline.process_issue(_make_issue(), issue_body="bug")

        # Coder was still called
        assert coder_called["value"]


# ---------------------------------------------------------------------------
# TS-82-19: Comment posting failure does not block pipeline
# Requirements: 82-REQ-3.E1, 82-REQ-6.E1
# ---------------------------------------------------------------------------


class TestCommentPostingResilience:
    """Verify comment posting failures are logged but don't stop pipeline."""

    @pytest.mark.asyncio
    async def test_comment_failure_continues(self) -> None:
        pipeline, mock_platform, _ = _make_pipeline()

        # Make comment posting fail
        mock_platform.add_issue_comment = AsyncMock(side_effect=Exception("API error"))

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            if archetype == "maintainer":
                return _make_session_outcome(_triage_json(1))
            if archetype == "reviewer":
                return _make_session_outcome(_review_json("PASS", ["AC-1"]))
            return _make_session_outcome()

        pipeline._run_session = mock_run_session  # type: ignore[method-assign]

        # Should not raise despite comment failures
        metrics = await pipeline.process_issue(_make_issue(), issue_body="bug")

        # At least coder + reviewer ran
        assert metrics.sessions_run >= 2


# ---------------------------------------------------------------------------
# TS-82-20: Only coder is retried, not triage or reviewer
# Requirement: 82-REQ-8.E1
# ---------------------------------------------------------------------------


class TestOnlyCoderRetried:
    """Verify triage runs once and reviewer is not independently retried."""

    @pytest.mark.asyncio
    async def test_triage_once_coder_and_reviewer_three_times(self) -> None:
        pipeline, mock_platform, _ = _make_pipeline(max_retries=3)

        archetype_counts: dict[str, int] = {}

        call_count = {"reviewer": 0}

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            archetype_counts[archetype] = archetype_counts.get(archetype, 0) + 1
            if archetype == "maintainer":
                return _make_session_outcome(_triage_json(1))
            if archetype == "reviewer":
                call_count["reviewer"] += 1
                if call_count["reviewer"] < 3:
                    return _make_session_outcome(_review_json("FAIL", ["AC-1"], ["FAIL"]))
                return _make_session_outcome(_review_json("PASS", ["AC-1"]))
            return _make_session_outcome()

        pipeline._run_session = mock_run_session  # type: ignore[method-assign]

        await pipeline.process_issue(_make_issue(), issue_body="bug")

        assert archetype_counts.get("maintainer", 0) == 1
        assert archetype_counts.get("coder", 0) == 3
        assert archetype_counts.get("reviewer", 0) == 3


# ---------------------------------------------------------------------------
# TS-82-E2: Reviewer with no triage criteria falls back to issue text
# Requirement: 82-REQ-5.E1
# ---------------------------------------------------------------------------


class TestReviewerNoTriageCriteria:
    """Verify reviewer prompt adaptation when no criteria exist."""

    def test_empty_triage_reviewer_prompt_mentions_issue(self) -> None:
        pipeline, _, _ = _make_pipeline()

        from agent_fox.session.review_parser import parse_triage_output

        empty_triage = parse_triage_output("no json here", "fix-issue-42", "s1")

        from agent_fox.nightshift.spec_builder import build_in_memory_spec

        spec = build_in_memory_spec(_make_issue(), "fix the bug")

        system_prompt, _ = pipeline._build_reviewer_prompt(spec, empty_triage)

        # Should reference issue description or contain the issue context
        prompt_lower = system_prompt.lower()
        assert "issue" in prompt_lower or spec.system_context in system_prompt
