"""Live progress display with spinner and permanent lines.

Manages a single-line spinner showing current activity and permanent
milestone lines for task completion and failure events.  Also defines
the lightweight event dataclasses and formatting helpers that flow from
the session runner and orchestrator to the display.

Requirements: 18-REQ-1.1, 18-REQ-1.3, 18-REQ-1.E1, 18-REQ-1.E2,
              18-REQ-2.1, 18-REQ-2.E2, 18-REQ-2.E3,
              18-REQ-3.1, 18-REQ-3.3, 18-REQ-3.E1,
              18-REQ-4.1, 18-REQ-4.2, 18-REQ-4.3, 18-REQ-4.E1,
              18-REQ-6.1, 18-REQ-6.2, 18-REQ-6.E1
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from agent_fox.reporting.formatters import format_tokens
from agent_fox.ui.display import AppTheme

# ---------------------------------------------------------------------------
# Event types and formatting helpers (formerly ui/events.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    """SDK tool-use activity from a coding session."""

    node_id: str  # e.g. "03_session:2"
    tool_name: str  # e.g. "Read", "Bash", "Edit"
    argument: str  # abbreviated first argument
    turn: int = 0  # running turn count within the session
    tokens: int | None = None  # cumulative tokens (input + output)
    archetype: str | None = None  # e.g. "coder", "verifier"


@dataclass(frozen=True, slots=True)
class TaskEvent:
    """Orchestrator task state change."""

    node_id: str
    status: str  # "completed" | "failed" | "blocked" | "retry" | "disagreed"
    duration_s: float  # wall-clock seconds for the task
    error_message: str | None = None
    archetype: str | None = None  # e.g. "coder", "skeptic", "verifier"
    attempt: int | None = None  # retry attempt number
    escalated_from: str | None = None  # e.g. "STANDARD"
    escalated_to: str | None = None  # e.g. "ADVANCED"
    predecessor_node: str | None = None  # for disagreement lines


ActivityCallback = Callable[[ActivityEvent], None]
TaskCallback = Callable[[TaskEvent], None]

# Verb forms for tool names displayed in the spinner summary line.
_TOOL_VERBS: dict[str, str] = {
    "Read": "Reading",
    "Edit": "Editing",
    "Write": "Writing",
    "Bash": "Running command",
    "Grep": "Searching",
    "Glob": "Finding files",
    "Agent": "Running agent",
    "WebFetch": "Fetching",
    "WebSearch": "Searching web",
    "LSP": "Analyzing",
    "NotebookEdit": "Editing notebook",
    "thinking...": "Thinking",
}


def verbify_tool(tool_name: str) -> str:
    """Convert a tool name to its verb form for display.

    Returns the mapped verb if known, otherwise returns the raw name
    unchanged.
    """
    if tool_name in _TOOL_VERBS:
        return _TOOL_VERBS[tool_name]
    return tool_name


def abbreviate_arg(raw: str, max_len: int = 60) -> str:
    """Shorten a tool argument for display.

    - File paths: keep as many trailing path components as fit within
      max_len, prefixed with ``…/``. Falls back to basename only if
      even ``…/parent/basename`` exceeds max_len. If the path already
      fits within max_len, return it as-is.
    - Other strings: truncate to max_len with ``...`` suffix.
    - Empty strings: return as-is.

    Algorithm for paths:
    1. If the full path already fits, return it unchanged.
    2. Split on separator. Collect components from the right.
    3. Build candidate = ``…/`` + ``comp_n/.../basename``.
    4. While candidate length > max_len, drop the leftmost included
       component.
    5. If only the basename remains and it still exceeds max_len,
       truncate the basename itself with ``...``.
    """
    if not raw:
        return raw

    # Detect file paths
    is_path = "/" in raw or "\\" in raw
    if is_path:
        # If the path already fits, return as-is
        if len(raw) <= max_len:
            return raw

        # Split on the appropriate separator
        if "\\" in raw:
            parts = [p for p in raw.replace("\\", "/").split("/") if p]
        else:
            parts = [p for p in raw.split("/") if p]

        if not parts:
            return raw

        basename = parts[-1]

        # Try to fit as many trailing components as possible with …/ prefix
        prefix = "…/"

        # Start with just the basename
        included = [basename]
        for i in range(len(parts) - 2, -1, -1):
            candidate_parts = [parts[i]] + included
            candidate = prefix + "/".join(candidate_parts)
            if len(candidate) <= max_len:
                included = candidate_parts
            else:
                break

        if len(included) > 1 or (len(included) == 1 and included[0] != basename):
            result = prefix + "/".join(included)
            if len(result) <= max_len:
                return result

        # Fall back to basename only
        if len(basename) <= max_len:
            return basename

        # Basename itself exceeds max_len — truncate it
        if max_len >= 4:
            return basename[: max_len - 3] + "..."
        return basename[:max_len]

    # Truncate long non-path strings
    if len(raw) > max_len:
        return raw[: max_len - 3] + "..."

    return raw


def format_duration(seconds: float) -> str:
    """Format a duration for display.

    < 60s -> "Xs", >= 60s -> "Xm Ys"
    """
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, remainder = divmod(s, 60)
    return f"{m}m {remainder}s"


# ---------------------------------------------------------------------------
# Progress display
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# Icons for permanent lines
_CHECK = "\u2714"  # ✔
_CROSS = "\u2718"  # ✘
_RETRY = "\u27f3"  # ⟳


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
            # Route log messages through the Live console so they
            # appear above the spinner instead of corrupting it.
            self._register_live_console(self._live.console)
        self._started = True

    def stop(self) -> None:
        """Stop the spinner and clear the line."""
        self._register_live_console(None)
        if self._live is not None:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None
        self._started = False

    def on_activity(self, event: ActivityEvent) -> None:
        """Update the spinner line with new activity. Serialized via lock.

        Renders a two-line format when a tool argument is present::

            [turn 3 | 1.2k tokens] [node_id] Reading…
            ⎿  path/to/file.py

        For thinking (no argument), renders a single line::

            [turn 3 | 1.2k tokens] [node_id] Thinking…
        """
        if self._quiet:
            return
        with self._lock:
            width = self._get_terminal_width()
            verb = verbify_tool(event.tool_name)
            token_str = format_tokens(event.tokens)
            arch_label = f" [{event.archetype}]" if event.archetype else ""
            prefix = f"[turn {event.turn} | {token_str} tokens] "
            summary = f"{prefix}[{event.node_id}]{arch_label} {verb}…"

            if event.argument:
                detail = f"  \u23bf  {event.argument}"
                # Truncate each line independently
                if len(summary) > width:
                    summary = summary[: width - 3] + "..."
                if len(detail) > width:
                    detail = detail[: width - 3] + "..."
                text = f"{summary}\n{detail}"
            else:
                if len(summary) > width:
                    summary = summary[: width - 3] + "..."
                text = summary

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

    def print_status(self, text: str, style: str = "bold cyan") -> None:
        """Print a permanent status line above the spinner.

        Used by the night-shift engine to emit phase-transition lines
        (e.g. "Checking for af:fix issues…", "Starting hunt scan…").

        Requirements: 81-REQ-3.1
        """
        if self._quiet:
            return
        with self._lock:
            line = Text(text, style=style)
            if self._is_tty and self._live is not None:
                self._live.console.print(line)
            else:
                self._console.print(line, highlight=False)

    def update_spinner_text(self, text: str) -> None:
        """Update the spinner text directly (e.g. for idle state display).

        Requirements: 81-REQ-4.1
        """
        if self._quiet:
            return
        with self._lock:
            self._spinner_text = text
            if self._live is not None:
                self._live.update(Spinner("dots", text=text))

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

    @staticmethod
    def _register_live_console(console: Console | None) -> None:
        """Register or unregister a Rich console with the live-aware log handler."""
        from agent_fox.core.logging import get_live_handler

        handler = get_live_handler()
        if handler is not None:
            handler.set_live_console(console)

    def _format_task_line(self, event: TaskEvent) -> Text:
        """Format a permanent line for a task event."""
        duration = format_duration(event.duration_s)
        arch_label = f" [{event.archetype}]" if event.archetype else ""

        if event.status == "completed":
            text = f"{_CHECK} {event.node_id}{arch_label} done ({duration})"
            return Text(text, style="bold green")
        elif event.status == "failed":
            text = f"{_CROSS} {event.node_id}{arch_label} failed"
            return Text(text, style="bold red")
        elif event.status == "blocked":
            text = f"{_CROSS} {event.node_id}{arch_label} blocked"
            return Text(text, style="bold red")
        elif event.status == "disagreed":
            pred = event.predecessor_node or ""
            text = f"{_CROSS} {event.node_id}{arch_label} disagrees → retry {pred}"
            return Text(text, style="bold yellow")
        elif event.status == "retry":
            attempt = event.attempt or 1
            base = f"{_RETRY} {event.node_id}{arch_label} retry #{attempt}"
            if event.escalated_from:
                base += f" (escalated: {event.escalated_from} → {event.escalated_to})"
            return Text(base, style="bold yellow")
        else:
            text = f"{_CROSS} {event.node_id}{arch_label} {event.status}"
            return Text(text, style="bold red")


class PlanSpinner:
    """Animated braille spinner on stderr for plan initialization.

    Displays a cycling braille character followed by a message on a single
    terminal line, overwriting itself with carriage return. The animation
    runs on a daemon thread and is one-shot: once stopped, start() is a no-op.
    """

    _FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
    _INTERVAL = 0.08  # seconds

    def __init__(self, message: str = "Planning...") -> None:
        self._message = message
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = False
        self._stopped = False

    def start(self) -> None:
        """Start the animation thread. No-op if already started or non-TTY."""
        import sys

        if self._started or not (hasattr(sys.stderr, "isatty") and sys.stderr.isatty()):
            return
        self._started = True
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def _animate(self) -> None:
        """Animation loop running on the daemon thread."""
        import sys

        idx = 0
        num_frames = len(self._FRAMES)
        try:
            while not self._stop_event.is_set():
                frame = self._FRAMES[idx % num_frames]
                sys.stderr.write(f"\r{frame} {self._message}")
                sys.stderr.flush()
                idx += 1
                self._stop_event.wait(self._INTERVAL)
        except Exception:
            logger.debug("PlanSpinner animation thread failed", exc_info=True)

    def stop(self) -> None:
        """Stop the animation and clear the spinner line."""
        import sys

        if not self._started or self._stopped:
            return
        self._stopped = True
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if hasattr(sys.stderr, "isatty") and sys.stderr.isatty():
            clear_len = len(self._message) + 4
            sys.stderr.write("\r" + " " * clear_len + "\r")
            sys.stderr.flush()

    @property
    def is_running(self) -> bool:
        """True while the animation thread is active."""
        return self._started and not self._stopped
