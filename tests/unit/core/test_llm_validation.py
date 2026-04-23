"""Tests for LLM response validation utilities.

Regression tests for GitHub issue #186: LLM JSON responses
deserialized without schema validation.
"""

from __future__ import annotations

from agent_fox.core.llm_validation import (
    MAX_CONTENT_LENGTH,
    truncate_field,
)


class TestTruncateField:
    """String field truncation."""

    def test_short_string_unchanged(self) -> None:
        assert truncate_field("hello", max_length=100, field_name="f") == "hello"

    def test_long_string_truncated(self) -> None:
        result = truncate_field("x" * 200, max_length=50, field_name="content")
        assert len(result) == 50
        assert result == "x" * 50

    def test_exact_length_unchanged(self) -> None:
        text = "a" * 100
        assert truncate_field(text, max_length=100, field_name="f") == text

    def test_empty_string_unchanged(self) -> None:
        assert truncate_field("", max_length=100, field_name="f") == ""


class TestMaxContentLengthConstant:
    """Verify MAX_CONTENT_LENGTH is reasonable."""

    def test_max_content_length_is_5000(self) -> None:
        assert MAX_CONTENT_LENGTH == 5000
