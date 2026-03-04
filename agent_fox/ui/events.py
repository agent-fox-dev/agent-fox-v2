"""Event types for live progress display.

Defines lightweight event dataclasses flowing from the session runner
and orchestrator to the progress display, plus argument abbreviation.

Requirements: 18-REQ-2.1, 18-REQ-2.E2, 18-REQ-2.E3, 18-REQ-4.1
"""

from __future__ import annotations

import ntpath
import os
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    """SDK tool-use activity from a coding session."""

    node_id: str  # e.g. "03_session:2"
    tool_name: str  # e.g. "Read", "Bash", "Edit"
    argument: str  # abbreviated first argument


@dataclass(frozen=True, slots=True)
class TaskEvent:
    """Orchestrator task state change."""

    node_id: str
    status: str  # "completed" | "failed" | "blocked"
    duration_s: float  # wall-clock seconds for the task
    error_message: str | None = None


ActivityCallback = Callable[[ActivityEvent], None]
TaskCallback = Callable[[TaskEvent], None]


def abbreviate_arg(raw: str, max_len: int = 30) -> str:
    """Shorten a tool argument for display.

    - File paths (containing / or \\): return basename only.
    - Other strings: truncate to max_len with ellipsis.
    - Empty strings: return as-is.
    """
    if not raw:
        return raw

    # Detect file paths and extract basename
    if "/" in raw or "\\" in raw:
        # Use ntpath for Windows-style paths (backslash), os.path for Unix
        basename = ntpath.basename(raw) if "\\" in raw else os.path.basename(raw)
        return basename

    # Truncate long strings
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
