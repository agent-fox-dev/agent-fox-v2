"""Unit tests for the JsonOutput helper module.

Test Spec: TS-23-19, TS-23-20, TS-23-24
Requirements: 23-REQ-7.1, 23-REQ-7.2, 23-REQ-7.3, 23-REQ-7.E1,
              23-REQ-7.E2, 23-REQ-8.4, 23-REQ-8.5
"""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest


class TestEmit:
    """Test json_io.emit() — single JSON object to stdout."""

    def test_emit_writes_valid_json(self) -> None:
        """emit() produces valid JSON output."""
        from agent_fox.cli.json_io import emit

        with patch("click.echo") as mock_echo:
            emit({"key": "value", "count": 42})
            output = mock_echo.call_args[0][0]
            data = json.loads(output)
            assert data == {"key": "value", "count": 42}

    def test_emit_handles_nested_data(self) -> None:
        """emit() handles nested structures."""
        from agent_fox.cli.json_io import emit

        nested = {"outer": {"inner": [1, 2, 3]}, "flag": True}
        with patch("click.echo") as mock_echo:
            emit(nested)
            output = mock_echo.call_args[0][0]
            data = json.loads(output)
            assert data == nested

    def test_emit_uses_indent(self) -> None:
        """emit() produces indented (pretty-printed) JSON."""
        from agent_fox.cli.json_io import emit

        with patch("click.echo") as mock_echo:
            emit({"a": 1})
            output = mock_echo.call_args[0][0]
            # Indented JSON has newlines
            assert "\n" in output

    def test_emit_handles_non_serializable_with_str(self) -> None:
        """emit() uses str() as default serializer for non-JSON types."""
        from pathlib import Path

        from agent_fox.cli.json_io import emit

        with patch("click.echo") as mock_echo:
            emit({"path": Path("/tmp/test")})
            output = mock_echo.call_args[0][0]
            data = json.loads(output)
            assert data["path"] == "/tmp/test"


class TestEmitLine:
    """Test json_io.emit_line() — compact JSONL output."""

    def test_emit_line_writes_valid_json(self) -> None:
        """emit_line() produces valid JSON."""
        from agent_fox.cli.json_io import emit_line

        with patch("click.echo") as mock_echo:
            emit_line({"event": "progress", "step": 1})
            output = mock_echo.call_args[0][0]
            data = json.loads(output)
            assert data == {"event": "progress", "step": 1}

    def test_emit_line_is_compact(self) -> None:
        """emit_line() produces single-line (non-indented) JSON."""
        from agent_fox.cli.json_io import emit_line

        with patch("click.echo") as mock_echo:
            emit_line({"a": 1, "b": 2})
            output = mock_echo.call_args[0][0]
            # Compact JSON has no newlines
            assert "\n" not in output


class TestEmitError:
    """Test json_io.emit_error() — error envelope output."""

    def test_emit_error_structure(self) -> None:
        """emit_error() produces {"error": "<message>"}."""
        from agent_fox.cli.json_io import emit_error

        with patch("click.echo") as mock_echo:
            emit_error("something went wrong")
            output = mock_echo.call_args[0][0]
            data = json.loads(output)
            assert data == {"error": "something went wrong"}

    def test_emit_error_non_empty_message(self) -> None:
        """emit_error() message is always a non-empty string."""
        from agent_fox.cli.json_io import emit_error

        with patch("click.echo") as mock_echo:
            emit_error("fail")
            output = mock_echo.call_args[0][0]
            data = json.loads(output)
            assert isinstance(data["error"], str)
            assert len(data["error"]) > 0


class TestReadStdin:
    """TS-23-19, TS-23-20: Test json_io.read_stdin()."""

    def test_read_stdin_parses_json(self) -> None:
        """TS-23-19: read_stdin() parses JSON from piped input."""
        from agent_fox.cli.json_io import read_stdin

        fake_stdin = io.StringIO('{"question": "what is fox?"}')
        fake_stdin.isatty = lambda: False  # type: ignore[method-assign]
        with patch("sys.stdin", fake_stdin):
            result = read_stdin()
            assert result == {"question": "what is fox?"}

    def test_read_stdin_tty_returns_empty(self) -> None:
        """TS-23-20: read_stdin() returns {} immediately for TTY."""
        from agent_fox.cli.json_io import read_stdin

        fake_stdin = io.StringIO("")
        fake_stdin.isatty = lambda: True  # type: ignore[method-assign]
        with patch("sys.stdin", fake_stdin):
            result = read_stdin()
            assert result == {}

    def test_read_stdin_empty_input(self) -> None:
        """read_stdin() returns {} for empty piped input."""
        from agent_fox.cli.json_io import read_stdin

        fake_stdin = io.StringIO("")
        fake_stdin.isatty = lambda: False  # type: ignore[method-assign]
        with patch("sys.stdin", fake_stdin):
            result = read_stdin()
            assert result == {}

    def test_read_stdin_invalid_json_raises(self) -> None:
        """TS-23-E6: read_stdin() raises on invalid JSON."""
        from agent_fox.cli.json_io import read_stdin

        fake_stdin = io.StringIO("not valid json {")
        fake_stdin.isatty = lambda: False  # type: ignore[method-assign]
        with patch("sys.stdin", fake_stdin):
            with pytest.raises(json.JSONDecodeError):
                read_stdin()

    def test_read_stdin_unknown_fields_preserved(self) -> None:
        """TS-23-E7: Unknown fields in stdin JSON are returned (caller ignores)."""
        from agent_fox.cli.json_io import read_stdin

        fake_stdin = io.StringIO('{"unknown_field": 42, "question": "test"}')
        fake_stdin.isatty = lambda: False  # type: ignore[method-assign]
        with patch("sys.stdin", fake_stdin):
            result = read_stdin()
            assert result["question"] == "test"
            # Unknown fields are present — caller decides what to use
            assert result["unknown_field"] == 42


class TestYamlRemovedFromEnum:
    """TS-23-24: OutputFormat has no YAML member."""

    def test_yaml_not_in_enum(self) -> None:
        """23-REQ-8.4: YAML is not in OutputFormat members."""
        from agent_fox.reporting.formatters import OutputFormat

        assert "YAML" not in OutputFormat.__members__

    def test_yaml_formatter_removed(self) -> None:
        """23-REQ-8.5: YamlFormatter does not exist."""
        from agent_fox.reporting import formatters

        assert not hasattr(formatters, "YamlFormatter")
