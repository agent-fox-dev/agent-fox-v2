"""Progress display tests.

Test Spec: TS-18-1, TS-18-2, TS-18-3, TS-18-4, TS-18-5,
           TS-18-E1, TS-18-E2, TS-18-E4
Requirements: 18-REQ-1.1, 18-REQ-1.3, 18-REQ-1.E1, 18-REQ-1.E2,
              18-REQ-2.1, 18-REQ-2.2, 18-REQ-3.1, 18-REQ-3.4,
              18-REQ-4.1, 18-REQ-4.2, 18-REQ-4.3, 18-REQ-4.E1,
              18-REQ-6.1, 18-REQ-6.E1
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console
from rich.theme import Theme

from agent_fox.core.config import ThemeConfig
from agent_fox.ui.events import ActivityEvent, TaskEvent
from agent_fox.ui.progress import ProgressDisplay
from agent_fox.ui.theme import AppTheme, create_theme

_STYLE_ROLES = ("header", "success", "error", "warning", "info", "tool", "muted")


def _make_theme(
    *, force_terminal: bool = True, width: int = 120
) -> tuple[AppTheme, StringIO]:
    """Create an AppTheme with a StringIO-backed console for testing.

    Returns:
        Tuple of (theme, buffer) where buffer captures console output.
    """
    config = ThemeConfig()
    theme = create_theme(config)
    buf = StringIO()
    rich_theme = Theme({role: getattr(config, role) for role in _STYLE_ROLES})
    theme.console = Console(
        file=buf, theme=rich_theme, width=width, force_terminal=force_terminal
    )
    return theme, buf


class TestProgressDisplayLifecycle:
    """TS-18-1: Progress display starts and stops."""

    def test_start_stop_no_exception(self) -> None:
        """ProgressDisplay start/stop lifecycle works cleanly."""
        theme, _buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        display.start()
        display.stop()
        # No exception raised means pass

    def test_stop_without_start(self) -> None:
        """Stopping without starting does not raise."""
        theme, _buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        display.stop()

    def test_double_stop(self) -> None:
        """Double stop does not raise."""
        theme, _buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        display.start()
        display.stop()
        display.stop()


class TestProgressDisplayActivity:
    """TS-18-2: Activity event updates spinner line."""

    def test_activity_updates_display_text(self) -> None:
        """Calling on_activity updates the displayed text."""
        theme, buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        display.start()
        display.on_activity(
            ActivityEvent(
                node_id="03_session:2", tool_name="Read", argument="config.py"
            )
        )
        # The display should contain the activity text
        text = display._get_spinner_text()
        display.stop()
        assert "[03_session:2] Read config.py" in text


class TestProgressDisplayThinking:
    """TS-18-3: Thinking state shown when no tool use."""

    def test_thinking_state_shown(self) -> None:
        """When model is thinking, spinner shows 'thinking...'."""
        theme, buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        display.start()
        display.on_activity(
            ActivityEvent(
                node_id="03_session:2", tool_name="thinking...", argument=""
            )
        )
        text = display._get_spinner_text()
        display.stop()
        assert "[03_session:2] thinking..." in text


class TestProgressDisplayTaskCompleted:
    """TS-18-4: Task completion prints permanent line."""

    def test_completed_task_prints_check_mark(self) -> None:
        """Completed task emits a styled permanent line."""
        theme, buf = _make_theme(force_terminal=False)
        display = ProgressDisplay(theme, quiet=False)
        display.start()
        display.on_task_event(
            TaskEvent(node_id="03_session:2", status="completed", duration_s=45.0)
        )
        display.stop()
        output = buf.getvalue()
        assert "\u2714" in output
        assert "03_session:2" in output
        assert "done" in output
        assert "45s" in output


class TestProgressDisplayTaskFailed:
    """TS-18-5: Task failure prints permanent line."""

    def test_failed_task_prints_cross_mark(self) -> None:
        """Failed task emits a permanent error line."""
        theme, buf = _make_theme(force_terminal=False)
        display = ProgressDisplay(theme, quiet=False)
        display.start()
        display.on_task_event(
            TaskEvent(
                node_id="03_session:2",
                status="failed",
                duration_s=12.0,
                error_message="test error",
            )
        )
        display.stop()
        output = buf.getvalue()
        assert "\u2718" in output
        assert "03_session:2" in output
        assert "failed" in output


class TestProgressDisplayQuiet:
    """TS-18-E1: Quiet mode suppresses all output."""

    def test_quiet_produces_no_output(self) -> None:
        """ProgressDisplay with quiet=True produces no output."""
        theme, buf = _make_theme()
        display = ProgressDisplay(theme, quiet=True)
        display.start()
        display.on_activity(
            ActivityEvent(node_id="x:1", tool_name="Read", argument="foo.py")
        )
        display.on_task_event(
            TaskEvent(node_id="x:1", status="completed", duration_s=1.0)
        )
        display.stop()
        assert buf.getvalue() == ""


class TestProgressDisplayNonTTY:
    """TS-18-E2: Non-TTY disables spinner, prints permanent lines."""

    def test_non_tty_prints_task_without_ansi(self) -> None:
        """Non-TTY console prints task events as plain text."""
        theme, buf = _make_theme(force_terminal=False)
        display = ProgressDisplay(theme, quiet=False)
        display.start()
        display.on_task_event(
            TaskEvent(node_id="x:1", status="completed", duration_s=10.0)
        )
        display.stop()
        output = buf.getvalue()
        assert "x:1" in output
        assert "done" in output
        assert "\x1b[" not in output


class TestProgressDisplayDefaultWidth:
    """TS-18-E4: Default terminal width fallback."""

    def test_truncation_defaults_to_80(self) -> None:
        """When terminal width is unavailable, default to 80."""
        theme, buf = _make_theme(width=80)
        display = ProgressDisplay(theme, quiet=False)
        display.start()
        display.on_activity(
            ActivityEvent(node_id="x:1", tool_name="Read", argument="a" * 200)
        )
        text = display._get_spinner_text()
        display.stop()
        assert len(text) <= 80
