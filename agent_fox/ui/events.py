"""Event types for live progress display.

Defines lightweight event dataclasses flowing from the session runner
and orchestrator to the progress display, plus argument abbreviation.

Requirements: 18-REQ-2.1, 18-REQ-2.E2, 18-REQ-2.E3, 18-REQ-4.1
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    """SDK tool-use activity from a coding session."""

    node_id: str  # e.g. "03_session:2"
    tool_name: str  # e.g. "Read", "Bash", "Edit"
    argument: str  # abbreviated first argument
    turn: int = 0  # running turn count within the session
    tokens: int | None = None  # cumulative tokens (input + output)


@dataclass(frozen=True, slots=True)
class TaskEvent:
    """Orchestrator task state change."""

    node_id: str
    status: str  # "completed" | "failed" | "blocked"
    duration_s: float  # wall-clock seconds for the task
    error_message: str | None = None


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

    Returns the mapped verb if known, otherwise appends ``…`` to the
    raw name.
    """
    if tool_name in _TOOL_VERBS:
        return _TOOL_VERBS[tool_name]
    # Generic fallback: capitalize and add ellipsis-style suffix
    return tool_name


def abbreviate_arg(raw: str, max_len: int = 30) -> str:
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
        # Start with all components except the first, then drop from the left
        prefix = "…/"

        # Try adding components from the right
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


def format_tokens(tokens: int | None) -> str:
    """Format token count for compact display.

    Returns "?k" if None, "X.YM" for millions, "X.Yk" for thousands.
    """
    if tokens is None:
        return "?k"
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    return f"{tokens / 1_000:.1f}k"


def format_duration(seconds: float) -> str:
    """Format a duration for display.

    < 60s -> "Xs", >= 60s -> "Xm Ys"
    """
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, remainder = divmod(s, 60)
    return f"{m}m {remainder}s"
