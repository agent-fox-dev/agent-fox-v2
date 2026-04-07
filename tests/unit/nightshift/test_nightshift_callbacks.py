"""Unit tests for callback plumbing: engine and fix pipeline.

Test Spec: TS-81-8, TS-81-9, TS-81-17, TS-81-18, TS-81-19, TS-81-E6
Requirements: 81-REQ-2.3, 81-REQ-2.4, 81-REQ-5.1, 81-REQ-5.2, 81-REQ-5.3,
              81-REQ-5.E1
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.platform.github import IssueResult
from agent_fox.ui.progress import TaskEvent


def _make_config() -> MagicMock:
    config = MagicMock()
    config.orchestrator.max_cost = None
    config.orchestrator.max_sessions = None
    config.night_shift.issue_check_interval = 900
    config.night_shift.hunt_scan_interval = 14400
    return config


def _make_issue(number: int = 42, title: str = "Fix bug") -> IssueResult:
    return IssueResult(
        number=number,
        title=title,
        html_url=f"https://github.com/test/repo/issues/{number}",
        body="Detailed bug description.",
    )


# ---------------------------------------------------------------------------
# TS-81-17: Engine constructor accepts callbacks
# Requirement: 81-REQ-5.1
# ---------------------------------------------------------------------------


class TestEngineConstructorCallbacks:
    """Verify NightShiftEngine stores callback parameters."""

    def test_81_constructor_accepts_callbacks(self) -> None:
        """NightShiftEngine constructor stores activity, task, and status callbacks."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = _make_config()
        platform = MagicMock()

        activity_cb = lambda e: None  # noqa: E731
        task_cb = lambda e: None  # noqa: E731
        status_cb = lambda text, style: None  # noqa: E731

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            activity_callback=activity_cb,
            task_callback=task_cb,
            status_callback=status_cb,
        )

        assert engine._activity_callback is activity_cb
        assert engine._task_callback is task_cb
        assert engine._status_callback is status_cb

    def test_81_constructor_defaults_none(self) -> None:
        """Callbacks default to None when not provided."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = _make_config()
        platform = MagicMock()

        engine = NightShiftEngine(config=config, platform=platform)

        assert engine._activity_callback is None
        assert engine._task_callback is None
        assert engine._status_callback is None


# ---------------------------------------------------------------------------
# TS-81-18: FixPipeline passes activity_callback to run_session
# Requirement: 81-REQ-5.2
# ---------------------------------------------------------------------------


class TestFixPipelinePassesCallback:
    """Verify FixPipeline forwards activity_callback to run_session."""

    @pytest.mark.asyncio
    async def test_81_callback_passed_to_session(self) -> None:
        """run_session receives activity_callback from FixPipeline."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        activity_cb = MagicMock()
        config = _make_config()
        platform = AsyncMock()

        pipeline = FixPipeline(
            config=config,
            platform=platform,
            activity_callback=activity_cb,
        )

        issue = _make_issue()

        mock_outcome = MagicMock(
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        # Capture calls to run_session via patching the session module
        captured_kwargs: list[dict] = []

        async def fake_run_session(**kwargs):
            captured_kwargs.append(kwargs)
            return mock_outcome

        with patch(
            "agent_fox.session.session.run_session",
            side_effect=fake_run_session,
        ):
            pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]
            pipeline._harvest_and_push = AsyncMock(return_value=True)  # type: ignore[method-assign]

            await pipeline.process_issue(issue, issue_body="Fix the bug")

        # Verify run_session was called with our activity_callback
        assert len(captured_kwargs) == 3  # skeptic, coder, verifier
        for kw in captured_kwargs:
            assert kw.get("activity_callback") is activity_cb

    @pytest.mark.asyncio
    async def test_81_none_callback_passed_to_session(self) -> None:
        """run_session receives None when no activity_callback provided."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = _make_config()
        platform = AsyncMock()

        pipeline = FixPipeline(config=config, platform=platform)

        issue = _make_issue()

        mock_outcome = MagicMock(
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        captured_kwargs: list[dict] = []

        async def fake_run_session(**kwargs):
            captured_kwargs.append(kwargs)
            return mock_outcome

        with patch(
            "agent_fox.session.session.run_session",
            side_effect=fake_run_session,
        ):
            pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]
            pipeline._harvest_and_push = AsyncMock(return_value=True)  # type: ignore[method-assign]

            await pipeline.process_issue(issue, issue_body="Fix the bug")

        for kw in captured_kwargs:
            assert kw.get("activity_callback") is None


# ---------------------------------------------------------------------------
# TS-81-9 / TS-81-19: FixPipeline emits TaskEvent per archetype
# Requirement: 81-REQ-2.4, 81-REQ-5.3
# ---------------------------------------------------------------------------


class TestFixPipelineTaskEvents:
    """Verify FixPipeline emits one TaskEvent per archetype."""

    @pytest.mark.asyncio
    async def test_81_task_event_per_archetype(self) -> None:
        """3 TaskEvents emitted with archetypes skeptic, coder, verifier."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        events: list[TaskEvent] = []
        config = _make_config()
        platform = AsyncMock()

        pipeline = FixPipeline(
            config=config,
            platform=platform,
            task_callback=events.append,
        )
        pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = AsyncMock(return_value=True)  # type: ignore[method-assign]

        mock_outcome = MagicMock(
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
        pipeline._run_session = AsyncMock(return_value=mock_outcome)  # type: ignore[method-assign]

        issue = _make_issue(number=42)

        await pipeline.process_issue(issue, issue_body="Fix the bug")

        assert len(events) == 3
        assert [e.archetype for e in events] == ["skeptic", "coder", "verifier"]
        assert all(e.status == "completed" for e in events)

    @pytest.mark.asyncio
    async def test_81_task_event_fields(self) -> None:
        """TaskEvents have correct node_id, positive duration, and archetype."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        events: list[TaskEvent] = []
        config = _make_config()
        platform = AsyncMock()

        pipeline = FixPipeline(
            config=config,
            platform=platform,
            task_callback=events.append,
        )
        pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = AsyncMock(return_value=True)  # type: ignore[method-assign]

        mock_outcome = MagicMock(
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
        pipeline._run_session = AsyncMock(return_value=mock_outcome)  # type: ignore[method-assign]

        issue = _make_issue(number=99)

        await pipeline.process_issue(issue, issue_body="Fix the bug")

        for e in events:
            assert e.duration_s >= 0
            assert e.node_id.startswith("fix-issue-99")
            assert e.status == "completed"
            assert e.archetype in ("skeptic", "coder", "verifier")

    @pytest.mark.asyncio
    async def test_81_task_event_on_failure(self) -> None:
        """TaskEvent with status='failed' emitted when session fails."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        events: list[TaskEvent] = []
        config = _make_config()
        platform = AsyncMock()

        pipeline = FixPipeline(
            config=config,
            platform=platform,
            task_callback=events.append,
        )
        pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]

        # First session (skeptic) fails
        pipeline._run_session = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("session crash")
        )

        issue = _make_issue(number=10)

        await pipeline.process_issue(issue, issue_body="Fix the bug")

        # Only one event (the failed skeptic), since pipeline stops on failure
        assert len(events) == 1
        assert events[0].status == "failed"
        assert events[0].archetype == "skeptic"
        assert events[0].duration_s >= 0

    @pytest.mark.asyncio
    async def test_81_no_task_events_when_callback_none(self) -> None:
        """No task events emitted when task_callback is None."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = _make_config()
        platform = AsyncMock()

        # No task_callback
        pipeline = FixPipeline(config=config, platform=platform)
        pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = AsyncMock(return_value=True)  # type: ignore[method-assign]

        mock_outcome = MagicMock(
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
        pipeline._run_session = AsyncMock(return_value=mock_outcome)  # type: ignore[method-assign]

        issue = _make_issue()

        # Should not raise even without callback
        await pipeline.process_issue(issue, issue_body="Fix the bug")


# ---------------------------------------------------------------------------
# TS-81-8: ActivityEvent forwarded during fix session
# Requirement: 81-REQ-2.3
# ---------------------------------------------------------------------------


class TestActivityEventForwarded:
    """Verify ActivityEvents from session runner reach the callback."""

    @pytest.mark.asyncio
    async def test_81_activity_forwarded(self) -> None:
        """activity_callback receives events when run_session emits them."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.ui.progress import ActivityEvent

        events: list[ActivityEvent] = []
        config = _make_config()
        platform = AsyncMock()

        pipeline = FixPipeline(
            config=config,
            platform=platform,
            activity_callback=events.append,
        )
        pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = AsyncMock(return_value=True)  # type: ignore[method-assign]

        mock_outcome = MagicMock(
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        # Simulate run_session calling activity_callback
        async def fake_run_session(**kwargs):
            cb = kwargs.get("activity_callback")
            if cb:
                cb(
                    ActivityEvent(
                        node_id="fix-issue-42:0:skeptic",
                        tool_name="Read",
                        argument="file.py",
                        archetype="skeptic",
                    )
                )
            return mock_outcome

        with patch(
            "agent_fox.session.session.run_session",
            side_effect=fake_run_session,
        ):
            await pipeline.process_issue(_make_issue(), issue_body="Fix the bug")

        # At least 3 events (one per archetype session)
        assert len(events) >= 3
        assert all(isinstance(e, ActivityEvent) for e in events)


# ---------------------------------------------------------------------------
# TS-81-E6: None callbacks produce no display output
# Requirement: 81-REQ-5.E1
# ---------------------------------------------------------------------------


class TestNoneCallbacks:
    """Verify engine operates normally without callbacks."""

    @pytest.mark.asyncio
    async def test_81_none_callbacks(self) -> None:
        """Engine and pipeline work with all callbacks set to None."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = _make_config()
        platform = AsyncMock()

        # No callbacks
        engine = NightShiftEngine(config=config, platform=platform)

        issue = _make_issue()

        mock_metrics = MagicMock(
            sessions_run=3,
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        with patch("agent_fox.nightshift.fix_pipeline.FixPipeline") as MockPipeline:
            mock_pipeline_instance = AsyncMock()
            mock_pipeline_instance.process_issue = AsyncMock(return_value=mock_metrics)
            MockPipeline.return_value = mock_pipeline_instance

            await engine._process_fix(issue)

        # No exception, state updated
        assert engine.state.issues_fixed == 1


# ---------------------------------------------------------------------------
# TS-81-5.1+5.5: Engine passes callbacks to FixPipeline
# Requirement: 81-REQ-5.1, 81-REQ-5.E1
# ---------------------------------------------------------------------------


class TestEnginePassesCallbacksToPipeline:
    """Verify engine forwards stored callbacks to FixPipeline."""

    @pytest.mark.asyncio
    async def test_81_callbacks_passed_to_pipeline(self) -> None:
        """FixPipeline receives activity and task callbacks from engine."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = _make_config()
        platform = AsyncMock()
        activity_cb = MagicMock()
        task_cb = MagicMock()

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            activity_callback=activity_cb,
            task_callback=task_cb,
        )

        issue = _make_issue()

        mock_metrics = MagicMock(
            sessions_run=3,
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        with patch("agent_fox.nightshift.fix_pipeline.FixPipeline") as MockPipeline:
            mock_pipeline_instance = AsyncMock()
            mock_pipeline_instance.process_issue = AsyncMock(return_value=mock_metrics)
            MockPipeline.return_value = mock_pipeline_instance

            await engine._process_fix(issue)

        # Verify FixPipeline was constructed with the callbacks
        call_kwargs = MockPipeline.call_args.kwargs
        assert call_kwargs["activity_callback"] is activity_cb
        assert call_kwargs["task_callback"] is task_cb
