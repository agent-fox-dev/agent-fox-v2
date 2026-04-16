"""Tests for the language analyzer framework.

Test Spec: TS-102-1, TS-102-2, TS-102-3, TS-102-4, TS-102-E3, TS-102-E4
Requirements: 102-REQ-1.1, 102-REQ-1.2, 102-REQ-1.3, 102-REQ-1.4, 102-REQ-1.E1, 102-REQ-1.E2
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# TS-102-1: Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    """TS-102-1: Every registered analyzer satisfies the LanguageAnalyzer protocol.

    Requirement: 102-REQ-1.1
    """

    def test_all_analyzers_satisfy_protocol(self) -> None:
        """Each analyzer in the default registry satisfies isinstance(a, LanguageAnalyzer)."""
        from agent_fox.knowledge.lang.base import LanguageAnalyzer
        from agent_fox.knowledge.lang.registry import get_default_registry

        registry = get_default_registry()
        analyzers = registry.all_analyzers()
        assert len(analyzers) > 0, "Default registry must contain at least one analyzer"
        for analyzer in analyzers:
            assert isinstance(analyzer, LanguageAnalyzer), f"{analyzer!r} does not satisfy LanguageAnalyzer protocol"

    def test_language_name_is_nonempty_string(self) -> None:
        """Each analyzer exposes a non-empty language_name string."""
        from agent_fox.knowledge.lang.registry import get_default_registry

        registry = get_default_registry()
        for analyzer in registry.all_analyzers():
            assert isinstance(analyzer.language_name, str), f"language_name for {analyzer!r} must be a str"
            assert len(analyzer.language_name) > 0, f"language_name for {analyzer!r} must be non-empty"

    def test_file_extensions_are_nonempty_dot_prefixed_strings(self) -> None:
        """Each analyzer has file_extensions as a non-empty set of dot-prefixed strings."""
        from agent_fox.knowledge.lang.registry import get_default_registry

        registry = get_default_registry()
        for analyzer in registry.all_analyzers():
            exts = analyzer.file_extensions
            assert isinstance(exts, set), f"{analyzer.language_name}.file_extensions must be a set"
            assert len(exts) > 0, f"{analyzer.language_name}.file_extensions must be non-empty"
            for ext in exts:
                assert isinstance(ext, str), f"Extension {ext!r} must be a string"
                assert ext.startswith("."), f"Extension {ext!r} must start with '.'"

    def test_make_parser_returns_non_none(self) -> None:
        """Each analyzer's make_parser() returns a non-None parser object."""
        from agent_fox.knowledge.lang.registry import get_default_registry

        registry = get_default_registry()
        for analyzer in registry.all_analyzers():
            parser = analyzer.make_parser()
            assert parser is not None, f"{analyzer.language_name}.make_parser() returned None"

    def test_required_methods_are_callable(self) -> None:
        """Each analyzer exposes callable extract_entities, extract_edges, build_module_map."""
        from agent_fox.knowledge.lang.registry import get_default_registry

        registry = get_default_registry()
        for analyzer in registry.all_analyzers():
            assert callable(getattr(analyzer, "extract_entities", None)), (
                f"{analyzer.language_name} missing callable extract_entities"
            )
            assert callable(getattr(analyzer, "extract_edges", None)), (
                f"{analyzer.language_name} missing callable extract_edges"
            )
            assert callable(getattr(analyzer, "build_module_map", None)), (
                f"{analyzer.language_name} missing callable build_module_map"
            )


# ---------------------------------------------------------------------------
# TS-102-2: Registry extension mapping
# ---------------------------------------------------------------------------


class TestRegistryExtensionMapping:
    """TS-102-2: Registry maps each file extension to exactly one analyzer.

    Requirement: 102-REQ-1.2
    """

    def test_registered_extension_returns_correct_analyzer(self) -> None:
        """get_analyzer returns the registered analyzer for a known extension."""
        from agent_fox.knowledge.lang.python_lang import PythonAnalyzer
        from agent_fox.knowledge.lang.registry import LanguageRegistry

        registry = LanguageRegistry()
        py_analyzer = PythonAnalyzer()
        registry.register(py_analyzer)

        result = registry.get_analyzer(".py")
        assert result is py_analyzer

    def test_duplicate_extension_raises_value_error(self) -> None:
        """Registering an extension already claimed by another analyzer raises ValueError."""
        from agent_fox.knowledge.lang.python_lang import PythonAnalyzer
        from agent_fox.knowledge.lang.registry import LanguageRegistry

        registry = LanguageRegistry()
        registry.register(PythonAnalyzer())

        class _ConflictingAnalyzer:
            """Fake analyzer that claims .py extension."""

            @property
            def language_name(self) -> str:
                return "fake"

            @property
            def file_extensions(self) -> set[str]:
                return {".py"}

            def make_parser(self):  # type: ignore[return]
                return None

            def extract_entities(self, tree, rel_path: str) -> list:
                return []

            def extract_edges(self, tree, rel_path: str, entities: list, module_map: dict) -> list:
                return []

            def build_module_map(self, repo_root: Path, files: list) -> dict:
                return {}

        with pytest.raises(ValueError, match=r"\.py"):
            registry.register(_ConflictingAnalyzer())  # type: ignore[arg-type]

    def test_unregistered_extension_returns_none(self) -> None:
        """get_analyzer returns None for extensions that are not registered."""
        from agent_fox.knowledge.lang.registry import LanguageRegistry

        registry = LanguageRegistry()
        assert registry.get_analyzer(".rs") is None
        assert registry.get_analyzer(".unknown") is None

    def test_all_analyzers_returns_registered_list(self) -> None:
        """all_analyzers() returns exactly the analyzers that were registered."""
        from agent_fox.knowledge.lang.python_lang import PythonAnalyzer
        from agent_fox.knowledge.lang.registry import LanguageRegistry

        registry = LanguageRegistry()
        py_analyzer = PythonAnalyzer()
        registry.register(py_analyzer)

        analyzers = registry.all_analyzers()
        assert py_analyzer in analyzers


# ---------------------------------------------------------------------------
# TS-102-3: Language detection
# ---------------------------------------------------------------------------


class TestLanguageDetection:
    """TS-102-3: detect_languages returns analyzers whose extensions match files present.

    Requirement: 102-REQ-1.3
    """

    def test_detect_returns_go_and_rust_for_go_and_rs_files(self, tmp_path: Path) -> None:
        """detect_languages returns GoAnalyzer and RustAnalyzer when .go and .rs files exist."""
        from agent_fox.knowledge.lang.registry import detect_languages

        (tmp_path / "main.go").write_text("package main\n")
        (tmp_path / "lib.rs").write_text("fn main() {}\n")

        detected = detect_languages(tmp_path)
        language_names = {a.language_name for a in detected}

        assert "go" in language_names, "GoAnalyzer should be detected for .go files"
        assert "rust" in language_names, "RustAnalyzer should be detected for .rs files"

    def test_detect_excludes_analyzers_with_no_matching_files(self, tmp_path: Path) -> None:
        """detect_languages excludes analyzers whose extensions have no files in the repo."""
        from agent_fox.knowledge.lang.registry import detect_languages

        (tmp_path / "main.go").write_text("package main\n")

        detected = detect_languages(tmp_path)
        language_names = {a.language_name for a in detected}

        assert "python" not in language_names, "PythonAnalyzer must not appear when no .py files exist"
        assert "java" not in language_names, "JavaAnalyzer must not appear when no .java files exist"

    def test_detect_returns_python_for_py_files(self, tmp_path: Path) -> None:
        """detect_languages returns PythonAnalyzer when .py files exist."""
        from agent_fox.knowledge.lang.registry import detect_languages

        (tmp_path / "app.py").write_text("# app\n")

        detected = detect_languages(tmp_path)
        language_names = {a.language_name for a in detected}

        assert "python" in language_names

    def test_detect_returns_empty_for_no_source_files(self, tmp_path: Path) -> None:
        """detect_languages returns an empty list when no recognized source files exist."""
        from agent_fox.knowledge.lang.registry import detect_languages

        (tmp_path / "README.md").write_text("# Docs\n")
        (tmp_path / "notes.txt").write_text("some notes")

        detected = detect_languages(tmp_path)
        assert detected == [], f"Expected empty list, got: {detected}"


# ---------------------------------------------------------------------------
# TS-102-4: File scanning
# ---------------------------------------------------------------------------


class TestFileScanning:
    """TS-102-4: _scan_files returns sorted files matching extensions, respecting .gitignore.

    Requirement: 102-REQ-1.4
    """

    def test_returns_only_files_with_matching_extensions(self, tmp_path: Path) -> None:
        """Files with non-matching extensions are excluded."""
        from agent_fox.knowledge.lang.registry import _scan_files

        (tmp_path / "a.py").write_text("# a")
        (tmp_path / "b.py").write_text("# b")
        (tmp_path / "c.txt").write_text("text")

        result = _scan_files(tmp_path, {".py"})
        names = {p.name for p in result}

        assert "a.py" in names
        assert "b.py" in names
        assert "c.txt" not in names

    def test_excludes_gitignored_files(self, tmp_path: Path) -> None:
        """Files matched by .gitignore are excluded from the result."""
        from agent_fox.knowledge.lang.registry import _scan_files

        (tmp_path / "a.py").write_text("# a")
        (tmp_path / "b.py").write_text("# b")
        (tmp_path / ".gitignore").write_text("b.py\n")

        result = _scan_files(tmp_path, {".py"})
        names = {p.name for p in result}

        assert "a.py" in names
        assert "b.py" not in names, "b.py must be excluded by .gitignore"

    def test_returns_paths_sorted_alphabetically(self, tmp_path: Path) -> None:
        """Returned paths are sorted alphabetically (ascending)."""
        from agent_fox.knowledge.lang.registry import _scan_files

        (tmp_path / "z.py").write_text("")
        (tmp_path / "a.py").write_text("")
        (tmp_path / "m.py").write_text("")

        result = _scan_files(tmp_path, {".py"})
        assert result == sorted(result), "Paths must be returned in alphabetical order"

    def test_returns_absolute_paths(self, tmp_path: Path) -> None:
        """Returned paths are absolute Path objects."""
        from agent_fox.knowledge.lang.registry import _scan_files

        (tmp_path / "a.py").write_text("")

        result = _scan_files(tmp_path, {".py"})
        assert len(result) == 1
        assert result[0].is_absolute(), "Returned paths must be absolute"


# ---------------------------------------------------------------------------
# TS-102-E3: Unregistered extension is skipped
# ---------------------------------------------------------------------------


class TestUnregisteredExtension:
    """TS-102-E3: Files with unregistered extensions produce no results.

    Requirement: 102-REQ-1.E1
    """

    def test_unregistered_extension_yields_no_files(self, tmp_path: Path) -> None:
        """_scan_files with known extensions does not return files with unknown extensions."""
        from agent_fox.knowledge.lang.registry import _scan_files

        (tmp_path / "file.xyz").write_text("content")
        (tmp_path / "another.abc").write_text("content")

        result = _scan_files(tmp_path, {".py", ".go", ".rs"})
        names = {p.name for p in result}

        assert "file.xyz" not in names
        assert "another.abc" not in names

    def test_get_analyzer_returns_none_for_unknown_extension(self) -> None:
        """get_analyzer on the default registry returns None for unrecognized extensions."""
        from agent_fox.knowledge.lang.registry import get_default_registry

        registry = get_default_registry()
        assert registry.get_analyzer(".xyz") is None
        assert registry.get_analyzer(".foobar") is None


# ---------------------------------------------------------------------------
# TS-102-E4: Non-git repo fallback
# ---------------------------------------------------------------------------


class TestNonGitRepoFallback:
    """TS-102-E4: _scan_files falls back to directory walk in non-git repositories.

    Requirement: 102-REQ-1.E2
    """

    def test_non_git_directory_returns_source_files(self, tmp_path: Path) -> None:
        """_scan_files works without a .gitignore or git repo and returns matching files."""
        from agent_fox.knowledge.lang.registry import _scan_files

        # tmp_path is not a git repository
        (tmp_path / "main.py").write_text("# main")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "helper.py").write_text("# helper")

        result = _scan_files(tmp_path, {".py"})
        names = {p.name for p in result}

        assert "main.py" in names
        assert "helper.py" in names

    def test_fallback_excludes_common_non_source_dirs(self, tmp_path: Path) -> None:
        """Non-git fallback excludes node_modules, .git, __pycache__, vendor, etc."""
        from agent_fox.knowledge.lang.registry import _scan_files

        # Create a file that should be found
        (tmp_path / "main.py").write_text("")

        # Create files in excluded directories that should NOT be found
        for excluded_dir in ("node_modules", ".git", "__pycache__", "vendor", "target", "build", "dist"):
            excl = tmp_path / excluded_dir
            excl.mkdir()
            (excl / "dep.py").write_text("")

        result = _scan_files(tmp_path, {".py"})
        names = {p.name for p in result}

        assert "main.py" in names
        # Files inside excluded dirs should not appear
        for excluded in ("node_modules", ".git", "__pycache__", "vendor", "target", "build", "dist"):
            for path in result:
                assert excluded not in path.parts, f"Found file inside excluded dir {excluded!r}: {path}"
