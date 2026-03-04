"""Property tests for progress display.

Test Spec: TS-18-P1, TS-18-P2, TS-18-P3, TS-18-P4
Properties: 1-4 from design.md
Requirements: 18-REQ-1.E1, 18-REQ-2.E2, 18-REQ-2.E3, 18-REQ-3.3,
              18-REQ-4.1, 18-REQ-4.2
"""

from __future__ import annotations

from io import StringIO

from agent_fox.ui.events import ActivityEvent, TaskEvent, abbreviate_arg
from agent_fox.ui.progress import ProgressDisplay
from hypothesis import given, settings
from hypothesis import strategies as st
from rich.console import Console
from rich.theme import Theme

from agent_fox.core.config import ThemeConfig
from agent_fox.ui.theme import AppTheme, create_theme

_STYLE_ROLES = ("header", "success", "error", "warning", "info", "tool", "muted")


def _make_theme(
    *, force_terminal: bool = True, width: int = 120
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


class TestSpinnerLineWidth:
    """TS-18-P1: Spinner line never exceeds terminal width.

    Property 1: For any text and terminal width, spinner line fits.
    """

    @given(
        text=st.text(min_size=0, max_size=200),
        width=st.integers(min_value=20, max_value=200),
    )
    @settings(max_examples=100)
    def test_spinner_line_fits_terminal(self, text: str, width: int) -> None:
        """Spinner line length never exceeds terminal width."""
        theme, _buf = _make_theme(width=width)
        display = ProgressDisplay(theme, quiet=False)
        display.start()
        display.on_activity(
            ActivityEvent(node_id="x:1", tool_name="Tool", argument=text)
        )
        line = display._get_spinner_text()
        display.stop()
        assert len(line) <= width, (
            f"Spinner line length {len(line)} exceeds width {width}: {line!r}"
        )


class TestAbbreviationIdempotence:
    """TS-18-P2: Abbreviation idempotence.

    Property 2: Abbreviating twice gives the same result as once.
    """

    @given(s=st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_abbreviation_is_idempotent(self, s: str) -> None:
        """abbreviate_arg(abbreviate_arg(s)) == abbreviate_arg(s)."""
        once = abbreviate_arg(s)
        twice = abbreviate_arg(once)
        assert twice == once, (
            f"Not idempotent for input {s!r}: first={once!r}, second={twice!r}"
        )


class TestQuietNoOutput:
    """TS-18-P3: Quiet produces no output.

    Property 3: Quiet display never writes to the console.
    """

    @given(
        node_ids=st.lists(
            st.text(min_size=1, max_size=20), min_size=1, max_size=20
        ),
        statuses=st.lists(
            st.sampled_from(["completed", "failed", "blocked"]),
            min_size=0,
            max_size=5,
        ),
    )
    @settings(max_examples=50)
    def test_quiet_never_writes(
        self, node_ids: list[str], statuses: list[str]
    ) -> None:
        """Quiet display produces empty output for any event sequence."""
        theme, buf = _make_theme()
        display = ProgressDisplay(theme, quiet=True)
        display.start()
        for nid in node_ids:
            display.on_activity(
                ActivityEvent(node_id=nid, tool_name="Read", argument="f.py")
            )
        for i, status in enumerate(statuses):
            nid = node_ids[i % len(node_ids)]
            display.on_task_event(
                TaskEvent(node_id=nid, status=status, duration_s=1.0)
            )
        display.stop()
        assert buf.getvalue() == "", (
            f"Expected no output in quiet mode, got: {buf.getvalue()!r}"
        )


class TestPermanentLinesContainNodeId:
    """TS-18-P4: Permanent lines contain node ID.

    Property 4: Every permanent line includes the node ID.
    """

    @given(
        node_id=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P"),
                whitelist_characters="_:",
            ),
            min_size=1,
            max_size=50,
        ),
        status=st.sampled_from(["completed", "failed", "blocked"]),
    )
    @settings(max_examples=50)
    def test_permanent_line_contains_node_id(
        self, node_id: str, status: str
    ) -> None:
        """Permanent line output contains the node ID."""
        theme, buf = _make_theme(force_terminal=False)
        display = ProgressDisplay(theme, quiet=False)
        display.start()
        display.on_task_event(
            TaskEvent(node_id=node_id, status=status, duration_s=1.0)
        )
        display.stop()
        output = buf.getvalue()
        assert node_id in output, (
            f"Node ID {node_id!r} not found in output: {output!r}"
        )
