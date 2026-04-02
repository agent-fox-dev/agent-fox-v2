"""Unit tests for steering document runtime loading (Spec 64).

Tests load_steering(), STEERING_PLACEHOLDER_SENTINEL, and placeholder detection.

Test Spec: TS-64-5, TS-64-7, TS-64-8, TS-64-E2
Requirements: 64-REQ-2.1, 64-REQ-2.3, 64-REQ-2.4, 64-REQ-2.E1,
              64-REQ-5.1, 64-REQ-5.2
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# TS-64-5: load_steering returns content for non-placeholder file
# Requirement: 64-REQ-2.1
# ---------------------------------------------------------------------------


class TestLoadSteeringReturnsContentForRealDirectives:
    """TS-64-5: load_steering() returns stripped content when file has directives."""

    def test_returns_content_string(self, tmp_path: Path) -> None:
        """load_steering() returns the file content (stripped) for real directives."""
        from agent_fox.session.prompt import load_steering

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        (specs_dir / "steering.md").write_text("Always use type hints.\n")

        result = load_steering(tmp_path)
        assert result == "Always use type hints."

    def test_returns_non_none_for_directive_content(self, tmp_path: Path) -> None:
        """load_steering() returns non-None when file contains user directives."""
        from agent_fox.session.prompt import load_steering

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        (specs_dir / "steering.md").write_text(
            "Never modify legacy/ without approval.\n"
        )

        result = load_steering(tmp_path)
        assert result is not None

    def test_content_is_stripped(self, tmp_path: Path) -> None:
        """Returned content has leading/trailing whitespace stripped."""
        from agent_fox.session.prompt import load_steering

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        (specs_dir / "steering.md").write_text("   Directive here.   \n\n")

        result = load_steering(tmp_path)
        assert result is not None
        assert result == result.strip()


# ---------------------------------------------------------------------------
# TS-64-7: Missing steering file skipped silently
# Requirement: 64-REQ-2.3
# ---------------------------------------------------------------------------


class TestLoadSteeringReturnNoneForMissingFile:
    """TS-64-7: load_steering() returns None when steering.md does not exist."""

    def test_returns_none_when_file_absent(self, tmp_path: Path) -> None:
        """load_steering() returns None when .specs/steering.md does not exist."""
        from agent_fox.session.prompt import load_steering

        result = load_steering(tmp_path)
        assert result is None

    def test_no_exception_when_file_absent(self, tmp_path: Path) -> None:
        """load_steering() does not raise when steering.md is absent."""
        from agent_fox.session.prompt import load_steering

        # Should not raise
        load_steering(tmp_path)

    def test_returns_none_when_specs_dir_absent(self, tmp_path: Path) -> None:
        """load_steering() returns None when .specs/ directory does not exist."""
        from agent_fox.session.prompt import load_steering

        # tmp_path has no .specs directory
        result = load_steering(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# TS-64-8: Placeholder-only file returns None
# Requirements: 64-REQ-2.4, 64-REQ-5.2
# ---------------------------------------------------------------------------


class TestLoadSteeringReturnNoneForPlaceholderOnly:
    """TS-64-8: load_steering() returns None for placeholder-only content."""

    def test_returns_none_for_placeholder(self, tmp_path: Path) -> None:
        """load_steering() returns None when file contains only the placeholder."""
        from agent_fox.workspace.init_project import _ensure_steering_md
        from agent_fox.session.prompt import load_steering

        _ensure_steering_md(tmp_path)
        result = load_steering(tmp_path)
        assert result is None

    def test_returns_none_for_sentinel_only(self, tmp_path: Path) -> None:
        """load_steering() returns None when file contains only the sentinel."""
        from agent_fox.session.prompt import load_steering

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        (specs_dir / "steering.md").write_text("<!-- steering:placeholder -->\n")

        result = load_steering(tmp_path)
        assert result is None

    def test_returns_none_for_sentinel_with_html_comments(self, tmp_path: Path) -> None:
        """load_steering() returns None for sentinel plus HTML comment content."""
        from agent_fox.session.prompt import load_steering

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        content = (
            "<!-- steering:placeholder -->\n"
            "<!--\n"
            "  This is instructional text inside a comment.\n"
            "  It should not be treated as a directive.\n"
            "-->\n"
        )
        (specs_dir / "steering.md").write_text(content)

        result = load_steering(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# TS-64-E2: Unreadable steering file at runtime
# Requirement: 64-REQ-2.E1
# ---------------------------------------------------------------------------


class TestLoadSteeringHandlesUnreadableFile:
    """TS-64-E2: load_steering() returns None and logs warning for unreadable file."""

    def test_returns_none_on_permission_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_steering() returns None when read_text raises PermissionError."""
        from agent_fox.session.prompt import load_steering

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        steering_path = specs_dir / "steering.md"
        steering_path.write_text("Some directive")

        original_read_text = Path.read_text

        def failing_read_text(self, *args, **kwargs):
            if self == steering_path:
                raise PermissionError("permission denied")
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", failing_read_text)
        result = load_steering(tmp_path)
        assert result is None

    def test_logs_warning_on_permission_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A warning is logged when steering.md cannot be read."""
        from agent_fox.session.prompt import load_steering

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        steering_path = specs_dir / "steering.md"
        steering_path.write_text("Some directive")

        original_read_text = Path.read_text

        def failing_read_text(self, *args, **kwargs):
            if self == steering_path:
                raise PermissionError("permission denied")
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", failing_read_text)

        with caplog.at_level(logging.WARNING):
            load_steering(tmp_path)

        assert any(record.levelno >= logging.WARNING for record in caplog.records), (
            "Expected a warning to be logged"
        )
