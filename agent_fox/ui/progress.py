"""Live progress display with spinner and permanent lines.

Manages a single-line spinner showing current activity and permanent
milestone lines for task completion and failure events.

Requirements: 18-REQ-1.1, 18-REQ-1.3, 18-REQ-1.E1, 18-REQ-1.E2,
              18-REQ-3.1, 18-REQ-3.3, 18-REQ-3.E1,
              18-REQ-4.1, 18-REQ-4.2, 18-REQ-4.3, 18-REQ-4.E1,
              18-REQ-6.1, 18-REQ-6.2, 18-REQ-6.E1
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from agent_fox.ui.events import ActivityEvent, TaskEvent, format_duration
from agent_fox.ui.theme import AppTheme

logger = logging.getLogger(__name__)

# Icons for permanent lines
_CHECK = "\u2714"  # ✔
_CROSS = "\u2718"  # ✘


class ProgressDisplay:
    """Single-line spinner with permanent milestone lines.

    Thread-safe: all public methods can be called from any asyncio task.
    The display owns a ``rich.live.Live`` context that renders to the
    theme's console.
    """

    def __init__(self, theme: AppTheme, *, quiet: bool = False) -> None:
        self._theme = theme
        self._quiet = quiet
        self._console = theme.console
        self._is_tty = self._console.is_terminal
        self._lock = threading.Lock()
        self._live: Live | None = None
        self._spinner_text = ""
        self._started = False

    def start(self) -> None:
        """Start the spinner. No-op if quiet or non-TTY."""
        if self._quiet:
            return
        if self._is_tty:
            self._live = Live(
                Spinner("dots", text=""),
                console=self._console,
                refresh_per_second=10,
                transient=True,
            )
            self._live.start()
        self._started = True

    def stop(self) -> None:
        """Stop the spinner and clear the line."""
        if self._live is not None:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None
        self._started = False

    def on_activity(self, event: ActivityEvent) -> None:
        """Update the spinner line with new activity. Serialized via lock."""
        if self._quiet:
            return
        with self._lock:
            # Format: [{node_id}] {tool_name} {argument}
            parts = [f"[{event.node_id}]", event.tool_name]
            if event.argument:
                parts.append(event.argument)
            text = " ".join(parts)

            # Truncate to terminal width
            width = self._get_terminal_width()
            if len(text) > width:
                text = text[: width - 3] + "..."

            self._spinner_text = text

            if self._live is not None:
                self._live.update(Spinner("dots", text=text))

    def on_task_event(self, event: TaskEvent) -> None:
        """Print a permanent line and continue the spinner below."""
        if self._quiet:
            return
        with self._lock:
            line = self._format_task_line(event)
            if self._is_tty and self._live is not None:
                # Print above the Live area
                self._live.console.print(line)
            else:
                # Non-TTY: plain print
                self._console.print(line, highlight=False)

    @property
    def activity_callback(self) -> Callable[[ActivityEvent], None]:
        """Callback suitable for passing to session runner."""
        return self.on_activity

    @property
    def task_callback(self) -> Callable[[TaskEvent], None]:
        """Callback suitable for passing to orchestrator."""
        return self.on_task_event

    def _get_spinner_text(self) -> str:
        """Return the current spinner text (for testing)."""
        return self._spinner_text

    def _get_terminal_width(self) -> int:
        """Get terminal width, defaulting to 80 if unavailable."""
        try:
            return self._console.width
        except Exception:
            return 80

    def _format_task_line(self, event: TaskEvent) -> Text:
        """Format a permanent line for a task event."""
        duration = format_duration(event.duration_s)

        if event.status == "completed":
            text = f"{_CHECK} {event.node_id} done ({duration})"
            return Text(text, style="bold green")
        elif event.status == "failed":
            text = f"{_CROSS} {event.node_id} failed"
            return Text(text, style="bold red")
        else:  # blocked
            text = f"{_CROSS} {event.node_id} blocked"
            return Text(text, style="bold red")
