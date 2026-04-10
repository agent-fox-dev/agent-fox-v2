"""Tests for scope_guard.source_parser module.

Requirements: 87-REQ-1.2, 87-REQ-2.1, 87-REQ-2.4, 87-REQ-2.E2
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.scope_guard.source_parser import (
    extract_all_functions,
    extract_function_body,
)


class TestExtractFunctionBody:
    """Basic tests for function body extraction."""

    def test_extract_rust_function(self, tmp_path: Path) -> None:
        src = tmp_path / "example.rs"
        src.write_text("fn hello() -> i32 {\n    42\n}\n")
        result = extract_function_body(src, "hello")
        assert result is not None
        assert result.function_id == "hello"
        assert "42" in result.body_text

    def test_extract_python_function(self, tmp_path: Path) -> None:
        src = tmp_path / "example.py"
        src.write_text("def hello():\n    return 42\n")
        result = extract_function_body(src, "hello")
        assert result is not None
        assert result.function_id == "hello"
        assert "return 42" in result.body_text

    def test_returns_none_for_missing_function(self, tmp_path: Path) -> None:
        src = tmp_path / "example.py"
        src.write_text("def hello():\n    return 42\n")
        result = extract_function_body(src, "nonexistent")
        assert result is None

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        result = extract_function_body(tmp_path / "missing.py", "hello")
        assert result is None


class TestExtractAllFunctions:
    """Tests for extracting all functions from a file."""

    def test_extracts_multiple_functions(self, tmp_path: Path) -> None:
        src = tmp_path / "example.py"
        src.write_text("def foo():\n    pass\n\ndef bar():\n    return 1\n")
        results = extract_all_functions(src)
        ids = {f.function_id for f in results}
        assert "foo" in ids
        assert "bar" in ids

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        src = tmp_path / "empty.py"
        src.write_text("")
        results = extract_all_functions(src)
        assert results == []
