"""Integration smoke tests for night-shift display.

Test Spec: TS-81-SMOKE-2
Requirements: 81-REQ-2.1, 81-REQ-2.3, 81-REQ-2.4,
              81-REQ-5.1, 81-REQ-5.2, 81-REQ-5.3

These tests use real FixPipeline with mock platform and session runner
to validate end-to-end wiring.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.platform.github import IssueResult
from agent_fox.ui.progress import ActivityEvent, TaskEvent
from agent_fox.workspace import WorkspaceInfo


def _mock_workspace() -> WorkspaceInfo:
    return WorkspaceInfo(
        path=Path("/tmp/mock-worktree"),
        branch="fix/test-branch",
        spec_name="fix-issue-42",
        task_group=0,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sdk_param_patches():
    """Return a contextlib.ExitStack with SDK param resolver patches."""
    import contextlib

    mock_model = MagicMock()
    mock_model.model_id = "mock-model-id"

    stack = contextlib.ExitStack()
    stack.enter_context(patch("agent_fox.core.models.resolve_model", return_value=mock_model))
    stack.enter_context(patch("agent_fox.engine.sdk_params.resolve_model_tier", return_value="standard"))
    stack.enter_context(patch("agent_fox.engine.sdk_params.resolve_security_config", return_value=None))
    stack.enter_context(patch("agent_fox.engine.sdk_params.resolve_max_turns", return_value=10))
    stack.enter_context(patch("agent_fox.engine.sdk_params.resolve_thinking", return_value=None))
    stack.enter_context(patch("agent_fox.engine.sdk_params.resolve_fallback_model", return_value=None))
    stack.enter_context(patch("agent_fox.engine.sdk_params.resolve_max_budget", return_value=None))
    return stack


def _make_config(
    *,
    max_cost: float | None = None,
    max_sessions: int | None = None,
) -> MagicMock:
    config = MagicMock()
    config.orchestrator.max_cost = max_cost
    config.orchestrator.max_sessions = max_sessions
    return config


def _make_issue(number: int = 42, title: str = "Fix linter warning") -> IssueResult:
    return IssueResult(
        number=number,
        title=title,
        html_url=f"https://github.com/test/repo/issues/{number}",
        body="Fix the linter warning in module.py.",
    )


# ---------------------------------------------------------------------------
# TS-81-SMOKE-2: Fix session activity display end-to-end
# ---------------------------------------------------------------------------


class TestFixSessionActivityDisplay:
    """End-to-end test: fix session produces ActivityEvents and TaskEvents
    that flow through the real FixPipeline to callbacks.
    """

    @pytest.mark.asyncio
    async def test_fix_session_activity_display(self) -> None:
        """Fix pipeline emits ActivityEvents and TaskEvents with correct fields."""
        import json

        from agent_fox.nightshift.fix_pipeline import FixPipeline

        issue = _make_issue(number=42)
        config = _make_config()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3
        platform = AsyncMock()

        activity_events: list[ActivityEvent] = []
        task_events: list[TaskEvent] = []

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

        # Simulate run_session emitting ActivityEvents
        async def fake_run_session(**kwargs):
            cb = kwargs.get("activity_callback")
            node_id = kwargs.get("node_id", "test")
            archetype = str(node_id).split(":")[-1] if node_id else "unknown"
            if cb:
                cb(
                    ActivityEvent(
                        node_id=str(node_id),
                        tool_name="Read",
                        argument="file.py",
                        turn=1,
                        tokens=100,
                        archetype=archetype,
                    )
                )
                cb(
                    ActivityEvent(
                        node_id=str(node_id),
                        tool_name="Edit",
                        argument="file.py",
                        turn=2,
                        tokens=200,
                        archetype=archetype,
                    )
                )
            mock_outcome = MagicMock(
                input_tokens=100,
                output_tokens=50,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
            if "triage" in str(node_id):
                mock_outcome.response = triage_response
            elif "fix_reviewer" in str(node_id):
                mock_outcome.response = review_response
            else:
                mock_outcome.response = ""
            return mock_outcome

        pipeline = FixPipeline(
            config=config,
            platform=platform,
            activity_callback=activity_events.append,
            task_callback=task_events.append,
        )
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = AsyncMock(return_value="merged")  # type: ignore[method-assign]

        with (
            patch(
                "agent_fox.session.session.run_session",
                side_effect=fake_run_session,
            ),
            _sdk_param_patches(),
        ):
            await pipeline.process_issue(issue, issue_body="Fix the linter warning")

        # Verify ActivityEvents were emitted (2 per archetype session = 6)
        assert len(activity_events) >= 6, f"Expected at least 6 activity events, got {len(activity_events)}"

        # Verify TaskEvents: one per archetype (triage + coder + fix_reviewer)
        archetype_names = [e.archetype for e in task_events]
        assert "triage" in archetype_names
        assert "coder" in archetype_names
        assert "fix_reviewer" in archetype_names
        assert all(e.status == "completed" for e in task_events)
        assert all(e.duration_s >= 0 for e in task_events)

        # Verify node_id format
        for e in task_events:
            assert e.node_id.startswith("fix-issue-42")
