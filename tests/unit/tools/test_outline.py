"""Outline tool unit tests.

Test Spec: TS-29-1 (symbols), TS-29-2 (imports), TS-29-3 (summary),
           TS-29-4 (multi-language),
           TS-29-E1 (missing file), TS-29-E2 (empty file), TS-29-E3 (binary file)
Requirements: 29-REQ-1.1, 29-REQ-1.2, 29-REQ-1.3, 29-REQ-1.4,
              29-REQ-1.E1, 29-REQ-1.E2, 29-REQ-1.E3
"""

from __future__ import annotations

from pathlib import Path


class TestOutlineReturnsSymbols:
    """TS-29-1: fox_outline returns symbols with kind, name, and line ranges."""

    def test_returns_symbols(self, sample_py: Path) -> None:
        from agent_fox.tools.outline import fox_outline
        from agent_fox.tools.types import OutlineResult

        result = fox_outline(str(sample_py))
        assert isinstance(result, OutlineResult)

        # sample.py has: foo, bar (functions), MyClass (class)
        non_import = [s for s in result.symbols if s.kind != "import_block"]
        assert len(non_import) >= 3

        names = {s.name for s in non_import}
        assert "foo" in names
        assert "bar" in names
        assert "MyClass" in names

        for s in result.symbols:
            assert s.start_line >= 1
            assert s.start_line <= s.end_line


class TestOutlineCollapsesImports:
    """TS-29-2: Contiguous import lines are collapsed into a summary entry."""

    def test_collapses_imports(self, make_temp_file) -> None:
        from agent_fox.tools.outline import fox_outline

        content = (
            "import os\n"
            "import sys\n"
            "import json\n"
            "import logging\n"
            "from pathlib import Path\n"
            "\n"
            "\n"
            "def my_func():\n"
            "    pass\n"
        )
        f = make_temp_file(content, "imports.py")
        result = fox_outline(str(f))

        import_blocks = [s for s in result.symbols if s.kind == "import_block"]
        assert len(import_blocks) >= 1
        assert "5 imports" in import_blocks[0].name
        assert import_blocks[0].start_line == 1
        assert import_blocks[0].end_line == 5


class TestOutlineSummary:
    """TS-29-3: OutlineResult includes total_lines and symbol count."""

    def test_summary_line(self, sample_py: Path) -> None:
        from agent_fox.tools.outline import fox_outline

        result = fox_outline(str(sample_py))

        # sample.py is ~30 lines
        assert result.total_lines > 0
        assert len(result.symbols) >= 3  # imports block + foo + bar + MyClass


class TestOutlineMultiLanguage:
    """TS-29-4: Heuristic parser detects declarations across languages."""

    def test_python(self, sample_py: Path) -> None:
        from agent_fox.tools.outline import fox_outline

        result = fox_outline(str(sample_py))
        names = {s.name for s in result.symbols if s.kind != "import_block"}
        assert {"foo", "bar", "MyClass"}.issubset(names)

    def test_javascript(self, sample_js: Path) -> None:
        from agent_fox.tools.outline import fox_outline

        result = fox_outline(str(sample_js))
        names = {s.name for s in result.symbols if s.kind != "import_block"}
        assert "greet" in names
        assert "Widget" in names

    def test_typescript(self, sample_ts: Path) -> None:
        from agent_fox.tools.outline import fox_outline

        result = fox_outline(str(sample_ts))
        names = {s.name for s in result.symbols if s.kind != "import_block"}
        assert "processData" in names
        assert "DataStore" in names

    def test_rust(self, sample_rs: Path) -> None:
        from agent_fox.tools.outline import fox_outline

        result = fox_outline(str(sample_rs))
        names = {s.name for s in result.symbols if s.kind != "import_block"}
        assert "compute" in names
        assert "Config" in names

    def test_go(self, sample_go: Path) -> None:
        from agent_fox.tools.outline import fox_outline

        result = fox_outline(str(sample_go))
        names = {s.name for s in result.symbols if s.kind != "import_block"}
        assert "greet" in names
        assert "Server" in names

    def test_java(self, sample_java: Path) -> None:
        from agent_fox.tools.outline import fox_outline

        result = fox_outline(str(sample_java))
        names = {s.name for s in result.symbols if s.kind != "import_block"}
        assert "Calculator" in names


class TestOutlineMissingFile:
    """TS-29-E1: Error returned for nonexistent file."""

    def test_missing_file(self) -> None:
        from agent_fox.tools.outline import fox_outline

        result = fox_outline("/nonexistent/path.py")
        assert isinstance(result, str)
        assert "/nonexistent/path.py" in result


class TestOutlineEmptyFile:
    """TS-29-E2: Empty file returns zero symbols and zero lines."""

    def test_empty_file(self, make_temp_file) -> None:
        from agent_fox.tools.outline import fox_outline
        from agent_fox.tools.types import OutlineResult

        f = make_temp_file("", "empty.py")
        result = fox_outline(str(f))
        assert isinstance(result, OutlineResult)
        assert result.symbols == []
        assert result.total_lines == 0


class TestOutlineBinaryFile:
    """TS-29-E3: Error for binary file."""

    def test_binary_file(self, tmp_path: Path) -> None:
        from agent_fox.tools.outline import fox_outline

        f = tmp_path / "binary.bin"
        f.write_bytes(b"Some text\x00\x01\x02 with null bytes")
        result = fox_outline(str(f))
        assert isinstance(result, str)
        assert "binary" in result.lower() or "text" in result.lower()
