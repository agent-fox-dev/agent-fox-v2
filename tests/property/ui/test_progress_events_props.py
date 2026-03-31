"""Property tests for progress display improvements.

Test Spec: TS-59-P1, TS-59-P2, TS-59-P3
Properties: 1-3 from design.md
Requirements: 59-REQ-6.1, 59-REQ-6.2, 59-REQ-7.1 through 59-REQ-7.3,
              59-REQ-8.2, 59-REQ-8.3, 59-REQ-8.E1
"""

from __future__ import annotations

from io import StringIO

from hypothesis import given, settings
from hypothesis import strategies as st
from rich.console import Console
from rich.theme import Theme

from agent_fox.core.config import ThemeConfig
from agent_fox.ui.display import AppTheme, create_theme
from agent_fox.ui.progress import ProgressDisplay, TaskEvent, abbreviate_arg

_STYLE_ROLES = ("header", "success", "error", "warning", "info", "tool", "muted")

_ARCHETYPES = [
    "coder",
    "skeptic",
    "verifier",
    "oracle",
    "auditor",
    "librarian",
    "cartographer",
]


def _make_theme(
    *, force_terminal: bool = False, width: int = 120
) -> tuple[AppTheme, StringIO]:
    """Create an AppTheme with a StringIO-backed console for testing."""
    config = ThemeConfig()
    theme = create_theme(config)
    buf = StringIO()
    rich_theme = Theme({role: getattr(config, role) for role in _STYLE_ROLES})
    theme.console = Console(
        file=buf, theme=rich_theme, width=width, force_terminal=force_terminal
    )
    return theme, buf


class TestTruncationLengthInvariant:
    """TS-59-P1: abbreviate_arg output never exceeds max_len.

    Property 1: For any string of length 0-500, max_len of 10-200,
    len(abbreviate_arg(s, max_len)) <= max_len.
    """

    @given(
        s=st.text(min_size=0, max_size=500),
        max_len=st.integers(min_value=10, max_value=200),
    )
    @settings(max_examples=200)
    def test_truncation_respects_limit(self, s: str, max_len: int) -> None:
        """abbreviate_arg result never exceeds max_len."""
        result = abbreviate_arg(s, max_len)
        assert len(result) <= max_len, (
            f"Result length {len(result)} exceeds max_len {max_len} "
            f"for input {s!r}: {result!r}"
        )


class TestArchetypeLabelPresence:
    """TS-59-P2: TaskEvent with archetype always produces [archetype] in line.

    Property 2: For any archetype in known set and status in
    {completed, failed, blocked}, the formatted line contains [archetype].
    """

    @given(
        archetype=st.sampled_from(_ARCHETYPES),
        status=st.sampled_from(["completed", "failed", "blocked"]),
    )
    @settings(max_examples=50)
    def test_archetype_in_formatted_line(self, archetype: str, status: str) -> None:
        """Formatted task line contains [archetype]."""
        theme, _buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        event = TaskEvent(
            node_id="s:1",
            status=status,
            duration_s=1.0,
            archetype=archetype,
        )
        line = display._format_task_line(event)
        text = str(line)
        assert f"[{archetype}]" in text, (
            f"Expected [{archetype}] in formatted line: {text!r}"
        )


class TestEventLineFormatCorrectness:
    """TS-59-P3: Retry events include attempt; escalation iff escalated_from set.

    Property 3: For any attempt 1-10, escalated_from in {None, SIMPLE, STANDARD},
    retry #{attempt} is always present; 'escalated:' present iff escalated_from
    is not None.
    """

    @given(
        attempt=st.integers(min_value=1, max_value=10),
        esc=st.sampled_from([None, "SIMPLE", "STANDARD"]),
    )
    @settings(max_examples=50)
    def test_retry_format_correctness(self, attempt: int, esc: str | None) -> None:
        """Retry lines always have attempt; escalation only when present."""
        theme, _buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        event = TaskEvent(
            node_id="s:1",
            status="retry",
            duration_s=0,
            archetype="coder",
            attempt=attempt,
            escalated_from=esc,
            escalated_to="ADVANCED" if esc else None,
        )
        line = display._format_task_line(event)
        text = str(line)
        assert f"retry #{attempt}" in text, f"Expected 'retry #{attempt}' in: {text!r}"
        assert ("escalated:" in text) == (esc is not None), (
            f"Escalation mismatch for esc={esc!r}: {text!r}"
        )
