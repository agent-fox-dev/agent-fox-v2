"""Event types and abbreviation tests.

Test Spec: TS-18-6, TS-18-7
Requirements: 18-REQ-2.E2, 18-REQ-2.E3
"""

from __future__ import annotations

from agent_fox.ui.events import ActivityEvent, TaskEvent, abbreviate_arg


class TestAbbreviateArgBasename:
    """TS-18-6: Abbreviate file path — trailing components."""

    def test_unix_path_abbreviated_with_trailing_components(self) -> None:
        """Long Unix paths abbreviated to trailing components."""
        result = abbreviate_arg(
            "/Users/dev/workspace/project/src/agent_fox/core/config.py"
        )
        # Default max_len=30; "…/src/agent_fox/core/config.py" is 30 chars (… is 1 char)
        assert result == "…/src/agent_fox/core/config.py"
        assert len(result) <= 30

    def test_windows_path_fits_returned_as_is(self) -> None:
        """Windows-style path that fits within max_len returned as-is."""
        result = abbreviate_arg(r"C:\Users\dev\project\config.py")
        # 30 chars == default max_len, fits
        assert result == r"C:\Users\dev\project\config.py"

    def test_relative_path_fits_returned_as_is(self) -> None:
        """Relative paths that fit within max_len are returned unchanged."""
        result = abbreviate_arg("src/agent_fox/core/config.py")
        # 29 chars < 30, fits
        assert result == "src/agent_fox/core/config.py"


class TestAbbreviateArgTrailingComponents:
    """TS-18-6, TS-18-11, TS-18-12, TS-18-13: Trailing path component abbreviation.

    Requirements: 18-REQ-2.E2
    """

    def test_long_path_abbreviated_to_trailing_components(self) -> None:
        """TS-18-6: Long path abbreviated to trailing components."""
        result = abbreviate_arg(
            "/Users/dev/workspace/project/src/agent_fox/core/config.py",
            max_len=30,
        )
        # "…/src/agent_fox/core/config.py" is exactly 30 chars (… is 1 char)
        assert result == "…/src/agent_fox/core/config.py"
        assert len(result) <= 30

    def test_path_falls_back_to_basename_when_tight(self) -> None:
        """TS-18-11: Falls back to basename when tight."""
        result = abbreviate_arg(
            "/a/very_long_directory_name/config.py", max_len=15
        )
        assert result == "config.py"

    def test_path_keeps_maximum_context(self) -> None:
        """TS-18-12: Abbreviation keeps as many trailing path components as possible."""
        result = abbreviate_arg(
            "/home/user/project/src/components/Button.tsx", max_len=40
        )
        assert "components/Button.tsx" in result
        assert result.startswith("…/")
        assert len(result) <= 40

    def test_short_path_returned_as_is(self) -> None:
        """TS-18-13: Paths that already fit within max_len are returned unchanged."""
        result = abbreviate_arg("src/config.py", max_len=30)
        assert result == "src/config.py"


class TestAbbreviateArgTruncation:
    """TS-18-7: Abbreviate long string with ellipsis."""

    def test_long_string_truncated_with_ellipsis(self) -> None:
        """Non-path strings exceeding max_len are truncated."""
        result = abbreviate_arg(
            "This is a very long argument that exceeds thirty characters easily",
            max_len=30,
        )
        assert len(result) == 30
        assert result.endswith("...")

    def test_short_string_unchanged(self) -> None:
        """Short strings are not truncated."""
        result = abbreviate_arg("short", max_len=30)
        assert result == "short"

    def test_empty_string_unchanged(self) -> None:
        """Empty strings are returned as-is."""
        result = abbreviate_arg("")
        assert result == ""

    def test_exact_max_len_unchanged(self) -> None:
        """Strings at exactly max_len are not truncated."""
        s = "x" * 30
        result = abbreviate_arg(s, max_len=30)
        assert result == s


class TestAbbreviateArgIdempotence:
    """Abbreviating twice gives the same result as once."""

    def test_path_idempotent(self) -> None:
        """Abbreviating a path twice yields same result."""
        once = abbreviate_arg("/a/b/c/file.py")
        twice = abbreviate_arg(once)
        assert twice == once

    def test_long_string_idempotent(self) -> None:
        """Abbreviating a long string twice yields same result."""
        once = abbreviate_arg("a" * 50, max_len=30)
        twice = abbreviate_arg(once, max_len=30)
        assert twice == once


class TestActivityEventConstruction:
    """ActivityEvent dataclass construction."""

    def test_basic_construction(self) -> None:
        """ActivityEvent can be constructed with required fields."""
        event = ActivityEvent(
            node_id="03_session:2", tool_name="Read", argument="config.py"
        )
        assert event.node_id == "03_session:2"
        assert event.tool_name == "Read"
        assert event.argument == "config.py"

    def test_frozen(self) -> None:
        """ActivityEvent is frozen (immutable)."""
        event = ActivityEvent(
            node_id="03_session:2", tool_name="Read", argument="config.py"
        )
        try:
            event.node_id = "other"  # type: ignore[misc]
            raise AssertionError("Expected FrozenInstanceError")
        except AttributeError:
            pass


class TestTaskEventConstruction:
    """TaskEvent dataclass construction."""

    def test_completed_event(self) -> None:
        """TaskEvent for completed task."""
        event = TaskEvent(node_id="03_session:2", status="completed", duration_s=45.0)
        assert event.node_id == "03_session:2"
        assert event.status == "completed"
        assert event.duration_s == 45.0
        assert event.error_message is None

    def test_failed_event_with_error(self) -> None:
        """TaskEvent for failed task with error message."""
        event = TaskEvent(
            node_id="03_session:2",
            status="failed",
            duration_s=12.0,
            error_message="test error",
        )
        assert event.status == "failed"
        assert event.error_message == "test error"

    def test_frozen(self) -> None:
        """TaskEvent is frozen (immutable)."""
        event = TaskEvent(node_id="x:1", status="completed", duration_s=1.0)
        try:
            event.status = "failed"  # type: ignore[misc]
            raise AssertionError("Expected FrozenInstanceError")
        except AttributeError:
            pass
