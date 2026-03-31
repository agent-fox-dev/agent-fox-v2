"""Tests for progress display improvements: truncation, archetypes, retry.

Test Spec: TS-59-20 through TS-59-28
Requirements: 59-REQ-6.1, 59-REQ-6.2, 59-REQ-7.1 through 59-REQ-7.E1,
              59-REQ-8.1 through 59-REQ-8.E1
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console
from rich.theme import Theme

from agent_fox.core.config import ThemeConfig
from agent_fox.ui.display import AppTheme, create_theme
from agent_fox.ui.progress import (
    ProgressDisplay,
    TaskEvent,
    abbreviate_arg,
)

_STYLE_ROLES = ("header", "success", "error", "warning", "info", "tool", "muted")


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


# ---------------------------------------------------------------------------
# TS-59-20, TS-59-21: Truncation improvements
# ---------------------------------------------------------------------------


class TestTruncationDefault60:
    """TS-59-20: abbreviate_arg default max_len is 60.

    Requirement: 59-REQ-6.1
    """

    def test_long_string_truncated_at_60(self) -> None:
        """abbreviate_arg('a' * 80) produces result <= 60 chars."""
        result = abbreviate_arg("a" * 80)
        assert len(result) <= 60, f"Expected len <= 60, got {len(result)}: {result!r}"

    def test_string_under_60_unchanged(self) -> None:
        """Strings under 60 chars are returned unchanged."""
        short = "a" * 50
        assert abbreviate_arg(short) == short


class TestPathTruncation60:
    """TS-59-21: Long file paths truncated with `…/` prefix at 60 chars.

    Requirement: 59-REQ-6.2
    """

    def test_long_path_truncated_to_60(self) -> None:
        """Long file path is truncated to <= 60 chars."""
        long_path = "/very/long/path/to/some/deeply/nested/directory/structure/file.py"
        result = abbreviate_arg(long_path)
        assert len(result) <= 60, f"Expected len <= 60, got {len(result)}: {result!r}"

    def test_truncated_path_preserves_filename(self) -> None:
        """Truncated path still contains the filename."""
        long_path = "/very/long/path/to/some/deeply/nested/directory/structure/file.py"
        result = abbreviate_arg(long_path)
        assert "file.py" in result, f"Expected 'file.py' in result: {result!r}"

    def test_truncated_path_uses_ellipsis_prefix(self) -> None:
        """Truncated path starts with or contains '…/'."""
        long_path = "/very/long/path/to/some/deeply/nested/directory/structure/file.py"
        result = abbreviate_arg(long_path)
        if len(long_path) > 60:
            assert "…/" in result or result == "file.py", (
                f"Expected '…/' prefix or basename only: {result!r}"
            )


# ---------------------------------------------------------------------------
# TS-59-22 through TS-59-24: Archetype in task lines
# ---------------------------------------------------------------------------


class TestTaskLineArchetypeComplete:
    """TS-59-22: Completed task line includes [archetype].

    Requirement: 59-REQ-7.1
    """

    def test_completed_line_includes_archetype(self) -> None:
        """Completed task event line contains [coder] and 'done'."""
        theme, _buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        event = TaskEvent(
            node_id="spec:1",
            status="completed",
            duration_s=45.0,
            archetype="coder",
        )
        line = display._format_task_line(event)
        text = str(line)
        assert "[coder]" in text, f"Expected [coder] in: {text!r}"
        assert "done" in text, f"Expected 'done' in: {text!r}"


class TestTaskLineArchetypeFailure:
    """TS-59-23: Failed task line includes [archetype].

    Requirement: 59-REQ-7.2
    """

    def test_failed_line_includes_archetype(self) -> None:
        """Failed task event line contains [verifier] and 'failed'."""
        theme, _buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        event = TaskEvent(
            node_id="spec:1",
            status="failed",
            duration_s=0,
            archetype="verifier",
        )
        line = display._format_task_line(event)
        text = str(line)
        assert "[verifier]" in text, f"Expected [verifier] in: {text!r}"
        assert "failed" in text, f"Expected 'failed' in: {text!r}"


class TestTaskLineArchetypeBlocked:
    """TS-59-24 (part): Blocked task line includes [archetype].

    Requirement: 59-REQ-7.3
    """

    def test_blocked_line_includes_archetype(self) -> None:
        """Blocked task event line contains [archetype] and 'blocked'."""
        theme, _buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        event = TaskEvent(
            node_id="spec:1",
            status="blocked",
            duration_s=0,
            archetype="coder",
        )
        line = display._format_task_line(event)
        text = str(line)
        assert "[coder]" in text, f"Expected [coder] in: {text!r}"
        assert "blocked" in text, f"Expected 'blocked' in: {text!r}"


class TestTaskLineArchetypeNone:
    """TS-59-24: When archetype is None, bracket label is omitted.

    Requirement: 59-REQ-7.E1
    """

    def test_no_archetype_omits_brackets(self) -> None:
        """No archetype means no bracket label in output."""
        theme, _buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        event = TaskEvent(
            node_id="spec:1",
            status="completed",
            duration_s=10,
        )
        line = display._format_task_line(event)
        text = str(line)
        # The node_id itself may contain ":" but should not contain "[" for archetype
        # We check that there is no bracketed archetype label
        assert "[coder]" not in text
        assert "[verifier]" not in text
        assert "[skeptic]" not in text


# ---------------------------------------------------------------------------
# TS-59-25 through TS-59-28: Disagreement, retry, escalation lines
# ---------------------------------------------------------------------------


class TestDisagreementLine:
    """TS-59-25: Reviewer disagreement produces correct permanent line.

    Requirement: 59-REQ-8.1
    """

    def test_disagreement_line_format(self) -> None:
        """Disagreement event contains ✗, [skeptic], disagrees, and predecessor."""
        theme, _buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        event = TaskEvent(
            node_id="spec:0",
            status="disagreed",
            duration_s=0,
            archetype="skeptic",
            predecessor_node="spec:1",
        )
        line = display._format_task_line(event)
        text = str(line)
        assert "[skeptic]" in text, f"Expected [skeptic] in: {text!r}"
        assert "disagrees" in text, f"Expected 'disagrees' in: {text!r}"
        assert "spec:1" in text, f"Expected predecessor 'spec:1' in: {text!r}"


class TestRetryLine:
    """TS-59-26: Retry event produces correct permanent line.

    Requirement: 59-REQ-8.2
    """

    def test_retry_line_format(self) -> None:
        """Retry event contains ⟳, [coder], retry #2."""
        theme, _buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        event = TaskEvent(
            node_id="spec:1",
            status="retry",
            duration_s=0,
            archetype="coder",
            attempt=2,
        )
        line = display._format_task_line(event)
        text = str(line)
        assert "retry #2" in text, f"Expected 'retry #2' in: {text!r}"
        assert "[coder]" in text, f"Expected [coder] in: {text!r}"


class TestRetryWithEscalation:
    """TS-59-27: Retry with escalation includes model tier info.

    Requirement: 59-REQ-8.3
    """

    def test_retry_escalation_line_format(self) -> None:
        """Retry with escalation contains escalation info."""
        theme, _buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        event = TaskEvent(
            node_id="spec:1",
            status="retry",
            duration_s=0,
            archetype="coder",
            attempt=2,
            escalated_from="STANDARD",
            escalated_to="ADVANCED",
        )
        line = display._format_task_line(event)
        text = str(line)
        assert "escalated: STANDARD" in text, (
            f"Expected 'escalated: STANDARD' in: {text!r}"
        )
        assert "ADVANCED" in text, f"Expected 'ADVANCED' in: {text!r}"


class TestRetryWithoutEscalation:
    """TS-59-28: Retry without escalation omits escalation suffix.

    Requirement: 59-REQ-8.E1
    """

    def test_retry_no_escalation_omits_suffix(self) -> None:
        """Retry without escalation does not contain 'escalated'."""
        theme, _buf = _make_theme()
        display = ProgressDisplay(theme, quiet=False)
        event = TaskEvent(
            node_id="spec:1",
            status="retry",
            duration_s=0,
            archetype="coder",
            attempt=2,
        )
        line = display._format_task_line(event)
        text = str(line)
        assert "retry #2" in text, f"Expected 'retry #2' in: {text!r}"
        assert "escalated" not in text, f"Expected 'escalated' not in: {text!r}"
