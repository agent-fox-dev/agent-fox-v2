"""Integration smoke tests for night-shift issue-first gate and display.

Test Spec: TS-81-SMOKE-1, TS-81-SMOKE-2, TS-81-SMOKE-3
Requirements: 81-REQ-1.1, 81-REQ-1.2, 81-REQ-1.3, 81-REQ-2.1, 81-REQ-2.3,
              81-REQ-2.4, 81-REQ-3.1, 81-REQ-3.2, 81-REQ-4.1, 81-REQ-4.2,
              81-REQ-5.1, 81-REQ-5.2, 81-REQ-5.3

These tests use real NightShiftEngine and FixPipeline with mock platform and
session runner to validate end-to-end wiring.
"""

from __future__ import annotations

import re
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.nightshift.engine import NightShiftEngine
from agent_fox.platform.github import IssueResult
from agent_fox.ui.progress import ActivityEvent, TaskEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    *,
    issue_interval: int = 900,
    hunt_interval: int = 14400,
    max_cost: float | None = None,
    max_sessions: int | None = None,
) -> MagicMock:
    config = MagicMock()
    config.night_shift.issue_check_interval = issue_interval
    config.night_shift.hunt_scan_interval = hunt_interval
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


def _make_theme(*, force_terminal: bool = True, width: int = 120) -> tuple:
    """Create an AppTheme with a StringIO-backed console for testing."""
    from rich.console import Console
    from rich.theme import Theme

    from agent_fox.core.config import ThemeConfig
    from agent_fox.ui.display import create_theme

    _STYLE_ROLES = ("header", "success", "error", "warning", "info", "tool", "muted")
    config = ThemeConfig()
    theme = create_theme(config)
    buf = StringIO()
    rich_theme = Theme({role: getattr(config, role) for role in _STYLE_ROLES})
    theme.console = Console(file=buf, theme=rich_theme, width=width, force_terminal=force_terminal)
    return theme, buf


# ---------------------------------------------------------------------------
# TS-81-SMOKE-1: Full startup with issue-first gate and display
# ---------------------------------------------------------------------------


class TestStartupIssueFirstDisplay:
    """End-to-end test: startup drains issues before hunt scan, display shows
    phase lines and activity events in correct order.

    Uses real NightShiftEngine (not mocked) with mock platform and session
    runner.
    """

    @pytest.mark.asyncio
    async def test_startup_issue_first_display(self) -> None:
        """Issue check runs before hunt scan, phase lines and task events appear."""
        issue = _make_issue(number=42, title="Fix linter warning")

        # Platform: returns 1 issue on first check, 0 after
        call_count = {"issue_check": 0}

        async def mock_list_issues(*args, **kwargs):
            call_count["issue_check"] += 1
            if call_count["issue_check"] <= 1:
                return [issue]
            return []

        platform = AsyncMock()
        platform.list_issues_by_label = AsyncMock(side_effect=mock_list_issues)
        platform.close_issue = AsyncMock()
        platform.add_issue_comment = AsyncMock()

        config = _make_config()

        # Track status lines and task events
        status_lines: list[tuple[str, str]] = []
        task_events: list[TaskEvent] = []
        activity_events: list[ActivityEvent] = []

        mock_outcome = MagicMock(
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            auto_fix=False,
            activity_callback=activity_events.append,
            task_callback=task_events.append,
            status_callback=lambda text, style: status_lines.append((text, style)),
        )

        # Mock the fix pipeline and hunt scan inner to avoid real I/O
        with (
            patch("agent_fox.nightshift.fix_pipeline.FixPipeline") as MockPipeline,
            patch.object(engine, "_run_hunt_scan_inner", new_callable=AsyncMock) as mock_hunt_inner,
        ):
            mock_pipeline_instance = AsyncMock()
            mock_pipeline_instance.process_issue = AsyncMock(return_value=mock_outcome)
            MockPipeline.return_value = mock_pipeline_instance
            mock_hunt_inner.return_value = []

            # Shutdown after startup completes
            engine.state.is_shutting_down = False

            async def shutdown_after_startup():
                state = await engine.run.__wrapped__(engine) if hasattr(engine.run, "__wrapped__") else None
                return state

            # Run with a task that shuts down quickly
            # We'll let the engine run its startup sequence then stop
            import asyncio

            async def run_engine_with_timeout():
                # Start the engine in a task
                task = asyncio.create_task(engine.run())
                # Give it enough time to complete startup sequence
                await asyncio.sleep(0.5)
                engine.request_shutdown()
                return await task

            state = await run_engine_with_timeout()

        # Verify issue check ran before hunt scan
        status_texts = [t for t, _ in status_lines]

        # Phase line for issue check should exist
        assert any("af:fix" in t or "issue" in t.lower() for t in status_texts), (
            f"Expected issue check phase line, got: {status_texts}"
        )

        # Phase line for hunt scan should exist
        assert any("hunt" in t.lower() or "scan" in t.lower() for t in status_texts), (
            f"Expected hunt scan phase line, got: {status_texts}"
        )

        # Issue check phase line should appear before hunt scan phase line
        issue_idx = next(i for i, t in enumerate(status_texts) if "af:fix" in t or "issue" in t.lower())
        hunt_idx = next(i for i, t in enumerate(status_texts) if "hunt" in t.lower() or "scan" in t.lower())
        assert issue_idx < hunt_idx, f"Issue check (idx {issue_idx}) should appear before hunt scan (idx {hunt_idx})"

        # At least 1 issue should have been fixed
        assert state.issues_fixed >= 1


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

        triage_response = json.dumps({
            "summary": "s", "affected_files": [],
            "acceptance_criteria": [
                {"id": "AC-1", "description": "d", "preconditions": "p",
                 "expected": "e", "assertion": "a"},
            ],
        })
        review_response = json.dumps({
            "verdicts": [{"criterion_id": "AC-1", "verdict": "PASS", "evidence": "ok"}],
            "overall_verdict": "PASS", "summary": "ok",
        })

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
                input_tokens=100, output_tokens=50,
                cache_read_input_tokens=0, cache_creation_input_tokens=0,
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
        pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = AsyncMock(return_value=True)  # type: ignore[method-assign]

        with patch(
            "agent_fox.session.session.run_session",
            side_effect=fake_run_session,
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


# ---------------------------------------------------------------------------
# TS-81-SMOKE-3: Idle state display end-to-end
# ---------------------------------------------------------------------------


class TestIdleStateDisplay:
    """End-to-end test: idle period shows next action time, clears on phase start."""

    @pytest.mark.asyncio
    async def test_idle_state_display(self) -> None:
        """Idle spinner shows 'Waiting until HH:MM' and clears on phase start."""
        config = _make_config(issue_interval=2, hunt_interval=5)
        platform = AsyncMock()
        platform.list_issues_by_label = AsyncMock(return_value=[])

        activity_events: list[ActivityEvent] = []
        status_lines: list[tuple[str, str]] = []

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            activity_callback=activity_events.append,
            status_callback=lambda text, style: status_lines.append((text, style)),
        )

        # Test idle spinner update directly
        engine._update_idle_spinner(300, 600)

        # Verify idle text contains expected format
        assert re.search(r"Waiting until \d{2}:\d{2}", engine._idle_text), (
            f"Expected 'Waiting until HH:MM' in idle text, got: {engine._idle_text}"
        )
        assert "issue check" in engine._idle_text, (
            f"Expected 'issue check' (earlier timer) in idle text, got: {engine._idle_text}"
        )

        # Verify ActivityEvent was emitted for spinner update
        assert len(activity_events) >= 1, "Expected at least 1 activity event for idle spinner"

        # Clear on phase start
        await engine._run_issue_check()
        assert engine._idle_text == "", f"Idle text should be cleared on phase start, got: {engine._idle_text}"

    def test_idle_timer_selection(self) -> None:
        """Idle spinner always displays the earlier of the two timers."""
        config = _make_config()
        platform = MagicMock()

        engine = NightShiftEngine(
            config=config,
            platform=platform,
            activity_callback=lambda e: None,
        )

        # Issue check sooner
        engine._update_idle_spinner(60, 3600)
        assert "issue check" in engine._idle_text

        # Hunt scan sooner
        engine._update_idle_spinner(3600, 60)
        assert "hunt scan" in engine._idle_text

        # Equal times: issue check wins (<=)
        engine._update_idle_spinner(300, 300)
        assert "issue check" in engine._idle_text
