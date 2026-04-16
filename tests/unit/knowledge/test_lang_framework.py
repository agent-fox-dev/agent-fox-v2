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

        # Only truly unrecognized extensions — .json and .html are now supported.
        (tmp_path / "README.md").write_text("# Docs\n")
        (tmp_path / "notes.txt").write_text("plain text")

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


# ---------------------------------------------------------------------------
# New language analyzers: bash, html, json, css, regex, swift
# ---------------------------------------------------------------------------


class TestNewLanguageAnalyzers:
    """Smoke tests for the six new language analyzers added in issue #426.

    Each test verifies:
    - make_parser() returns a non-None parser.
    - extract_entities() produces at least one FILE entity with the correct name.
    - extract_edges() and build_module_map() return valid (possibly empty) results.
    """

    # ------------------------------------------------------------------
    # Bash
    # ------------------------------------------------------------------

    def test_bash_make_parser(self) -> None:
        """BashAnalyzer.make_parser() returns a non-None parser."""
        from agent_fox.knowledge.lang.bash_lang import BashAnalyzer

        analyzer = BashAnalyzer()
        assert analyzer.make_parser() is not None

    def test_bash_extract_entities_file_and_functions(self) -> None:
        """BashAnalyzer extracts a FILE entity and FUNCTION entities for each shell function."""
        from agent_fox.knowledge.lang.bash_lang import BashAnalyzer
        from agent_fox.knowledge.entities import EntityType

        analyzer = BashAnalyzer()
        parser = analyzer.make_parser()
        source = b"#!/bin/bash\nfunction greet() { echo hello; }\ncleanup() { rm -f /tmp/x; }\n"
        tree = parser.parse(source)
        entities = analyzer.extract_entities(tree, "script.sh")

        names = {e.entity_name for e in entities}
        types = {e.entity_type for e in entities}

        assert "script.sh" in names, "FILE entity must have the file name"
        assert EntityType.FILE in types
        assert "greet" in names, "greet() function must be extracted"
        assert "cleanup" in names, "cleanup() function must be extracted"
        assert EntityType.FUNCTION in types

    def test_bash_extract_edges_contains(self) -> None:
        """BashAnalyzer.extract_edges() produces CONTAINS edges for each function."""
        from agent_fox.knowledge.lang.bash_lang import BashAnalyzer
        from agent_fox.knowledge.entities import EdgeType

        analyzer = BashAnalyzer()
        parser = analyzer.make_parser()
        source = b"my_func() { echo done; }\n"
        tree = parser.parse(source)
        entities = analyzer.extract_entities(tree, "run.sh")
        edges = analyzer.extract_edges(tree, "run.sh", entities, {})

        assert any(e.relationship == EdgeType.CONTAINS for e in edges), (
            "Expected at least one CONTAINS edge from file to function"
        )

    def test_bash_build_module_map_empty(self, tmp_path: Path) -> None:
        """BashAnalyzer.build_module_map() always returns an empty dict."""
        from agent_fox.knowledge.lang.bash_lang import BashAnalyzer

        analyzer = BashAnalyzer()
        mm = analyzer.build_module_map(tmp_path, [])
        assert mm == {}

    def test_bash_file_extensions(self) -> None:
        """BashAnalyzer.file_extensions includes .sh and .bash."""
        from agent_fox.knowledge.lang.bash_lang import BashAnalyzer

        analyzer = BashAnalyzer()
        assert ".sh" in analyzer.file_extensions
        assert ".bash" in analyzer.file_extensions

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def test_html_make_parser(self) -> None:
        """HtmlAnalyzer.make_parser() returns a non-None parser."""
        from agent_fox.knowledge.lang.html_lang import HtmlAnalyzer

        analyzer = HtmlAnalyzer()
        assert analyzer.make_parser() is not None

    def test_html_extract_entities_file_only(self) -> None:
        """HtmlAnalyzer extracts only a FILE entity."""
        from agent_fox.knowledge.lang.html_lang import HtmlAnalyzer
        from agent_fox.knowledge.entities import EntityType

        analyzer = HtmlAnalyzer()
        parser = analyzer.make_parser()
        source = b"<html><body><p>Hello</p></body></html>"
        tree = parser.parse(source)
        entities = analyzer.extract_entities(tree, "index.html")

        assert len(entities) == 1
        assert entities[0].entity_type == EntityType.FILE
        assert entities[0].entity_name == "index.html"

    def test_html_extract_edges_empty(self) -> None:
        """HtmlAnalyzer.extract_edges() always returns an empty list."""
        from agent_fox.knowledge.lang.html_lang import HtmlAnalyzer

        analyzer = HtmlAnalyzer()
        parser = analyzer.make_parser()
        tree = parser.parse(b"<p>hi</p>")
        entities = analyzer.extract_entities(tree, "page.html")
        assert analyzer.extract_edges(tree, "page.html", entities, {}) == []

    def test_html_file_extensions(self) -> None:
        """HtmlAnalyzer.file_extensions includes .html and .htm."""
        from agent_fox.knowledge.lang.html_lang import HtmlAnalyzer

        analyzer = HtmlAnalyzer()
        assert ".html" in analyzer.file_extensions
        assert ".htm" in analyzer.file_extensions

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def test_json_make_parser(self) -> None:
        """JsonAnalyzer.make_parser() returns a non-None parser."""
        from agent_fox.knowledge.lang.json_lang import JsonAnalyzer

        analyzer = JsonAnalyzer()
        assert analyzer.make_parser() is not None

    def test_json_extract_entities_file_only(self) -> None:
        """JsonAnalyzer extracts only a FILE entity."""
        from agent_fox.knowledge.lang.json_lang import JsonAnalyzer
        from agent_fox.knowledge.entities import EntityType

        analyzer = JsonAnalyzer()
        parser = analyzer.make_parser()
        source = b'{"key": "value"}'
        tree = parser.parse(source)
        entities = analyzer.extract_entities(tree, "config.json")

        assert len(entities) == 1
        assert entities[0].entity_type == EntityType.FILE
        assert entities[0].entity_name == "config.json"

    def test_json_extract_edges_empty(self) -> None:
        """JsonAnalyzer.extract_edges() always returns an empty list."""
        from agent_fox.knowledge.lang.json_lang import JsonAnalyzer

        analyzer = JsonAnalyzer()
        parser = analyzer.make_parser()
        tree = parser.parse(b"{}")
        entities = analyzer.extract_entities(tree, "data.json")
        assert analyzer.extract_edges(tree, "data.json", entities, {}) == []

    def test_json_detect_in_registry(self, tmp_path: Path) -> None:
        """detect_languages returns the json analyzer when .json files are present."""
        from agent_fox.knowledge.lang.registry import detect_languages

        (tmp_path / "config.json").write_text('{"ok": true}')
        detected = detect_languages(tmp_path)
        assert any(a.language_name == "json" for a in detected), (
            "JSON analyzer must be detected when .json files are present"
        )

    # ------------------------------------------------------------------
    # CSS
    # ------------------------------------------------------------------

    def test_css_make_parser(self) -> None:
        """CssAnalyzer.make_parser() returns a non-None parser."""
        from agent_fox.knowledge.lang.css_lang import CssAnalyzer

        analyzer = CssAnalyzer()
        assert analyzer.make_parser() is not None

    def test_css_extract_entities_file_only(self) -> None:
        """CssAnalyzer extracts only a FILE entity."""
        from agent_fox.knowledge.lang.css_lang import CssAnalyzer
        from agent_fox.knowledge.entities import EntityType

        analyzer = CssAnalyzer()
        parser = analyzer.make_parser()
        source = b".foo { color: red; }"
        tree = parser.parse(source)
        entities = analyzer.extract_entities(tree, "styles.css")

        assert len(entities) == 1
        assert entities[0].entity_type == EntityType.FILE
        assert entities[0].entity_name == "styles.css"

    def test_css_extract_edges_empty(self) -> None:
        """CssAnalyzer.extract_edges() always returns an empty list."""
        from agent_fox.knowledge.lang.css_lang import CssAnalyzer

        analyzer = CssAnalyzer()
        parser = analyzer.make_parser()
        tree = parser.parse(b"body { margin: 0; }")
        entities = analyzer.extract_entities(tree, "main.css")
        assert analyzer.extract_edges(tree, "main.css", entities, {}) == []

    # ------------------------------------------------------------------
    # Regex
    # ------------------------------------------------------------------

    def test_regex_make_parser(self) -> None:
        """RegexAnalyzer.make_parser() returns a non-None parser."""
        from agent_fox.knowledge.lang.regex_lang import RegexAnalyzer

        analyzer = RegexAnalyzer()
        assert analyzer.make_parser() is not None

    def test_regex_extract_entities_file_only(self) -> None:
        """RegexAnalyzer extracts only a FILE entity."""
        from agent_fox.knowledge.lang.regex_lang import RegexAnalyzer
        from agent_fox.knowledge.entities import EntityType

        analyzer = RegexAnalyzer()
        parser = analyzer.make_parser()
        source = b"[a-z]+"
        tree = parser.parse(source)
        entities = analyzer.extract_entities(tree, "pattern.regex")

        assert len(entities) == 1
        assert entities[0].entity_type == EntityType.FILE
        assert entities[0].entity_name == "pattern.regex"

    def test_regex_extract_edges_empty(self) -> None:
        """RegexAnalyzer.extract_edges() always returns an empty list."""
        from agent_fox.knowledge.lang.regex_lang import RegexAnalyzer

        analyzer = RegexAnalyzer()
        parser = analyzer.make_parser()
        tree = parser.parse(b"\\d+")
        entities = analyzer.extract_entities(tree, "digits.regex")
        assert analyzer.extract_edges(tree, "digits.regex", entities, {}) == []

    # ------------------------------------------------------------------
    # Swift
    # ------------------------------------------------------------------

    def test_swift_make_parser(self) -> None:
        """SwiftAnalyzer.make_parser() returns a non-None parser."""
        from agent_fox.knowledge.lang.swift_lang import SwiftAnalyzer

        analyzer = SwiftAnalyzer()
        assert analyzer.make_parser() is not None

    def test_swift_extract_entities_class_and_function(self) -> None:
        """SwiftAnalyzer extracts FILE, CLASS, and FUNCTION entities."""
        from agent_fox.knowledge.lang.swift_lang import SwiftAnalyzer
        from agent_fox.knowledge.entities import EntityType

        analyzer = SwiftAnalyzer()
        parser = analyzer.make_parser()
        source = b"class Animal {\n    func speak() {}\n}\nfunc topLevel() {}\n"
        tree = parser.parse(source)
        entities = analyzer.extract_entities(tree, "Animal.swift")

        names = {e.entity_name for e in entities}
        types = {e.entity_type for e in entities}

        assert "Animal.swift" in names, "FILE entity must have the file name"
        assert EntityType.FILE in types
        assert "Animal" in names, "CLASS entity must be extracted"
        assert EntityType.CLASS in types
        assert "Animal.speak" in names, "method must be qualified as ClassName.method"
        assert "topLevel" in names, "top-level function must be extracted"
        assert EntityType.FUNCTION in types

    def test_swift_extract_entities_struct(self) -> None:
        """SwiftAnalyzer extracts CLASS entity for struct declarations."""
        from agent_fox.knowledge.lang.swift_lang import SwiftAnalyzer
        from agent_fox.knowledge.entities import EntityType

        analyzer = SwiftAnalyzer()
        parser = analyzer.make_parser()
        source = b"struct Point { var x: Int }\n"
        tree = parser.parse(source)
        entities = analyzer.extract_entities(tree, "Point.swift")

        types_by_name = {e.entity_name: e.entity_type for e in entities}
        assert "Point" in types_by_name, "struct must produce a CLASS entity"
        assert types_by_name["Point"] == EntityType.CLASS

    def test_swift_extract_entities_protocol(self) -> None:
        """SwiftAnalyzer extracts CLASS entity for protocol declarations."""
        from agent_fox.knowledge.lang.swift_lang import SwiftAnalyzer
        from agent_fox.knowledge.entities import EntityType

        analyzer = SwiftAnalyzer()
        parser = analyzer.make_parser()
        source = b"protocol Runnable { func run() }\n"
        tree = parser.parse(source)
        entities = analyzer.extract_entities(tree, "Runnable.swift")

        names = {e.entity_name for e in entities}
        assert "Runnable" in names, "protocol must produce a CLASS entity"

    def test_swift_extract_edges_contains(self) -> None:
        """SwiftAnalyzer.extract_edges() produces CONTAINS edges."""
        from agent_fox.knowledge.lang.swift_lang import SwiftAnalyzer
        from agent_fox.knowledge.entities import EdgeType

        analyzer = SwiftAnalyzer()
        parser = analyzer.make_parser()
        source = b"class Foo { func bar() {} }\n"
        tree = parser.parse(source)
        entities = analyzer.extract_entities(tree, "Foo.swift")
        edges = analyzer.extract_edges(tree, "Foo.swift", entities, {})

        assert any(e.relationship == EdgeType.CONTAINS for e in edges), (
            "Expected CONTAINS edges for class and method"
        )

    def test_swift_build_module_map(self, tmp_path: Path) -> None:
        """SwiftAnalyzer.build_module_map() maps file stems to POSIX paths."""
        from agent_fox.knowledge.lang.swift_lang import SwiftAnalyzer

        swift_file = tmp_path / "MyModule.swift"
        swift_file.write_text("class Foo {}")
        analyzer = SwiftAnalyzer()
        mm = analyzer.build_module_map(tmp_path, [swift_file])
        assert "MyModule" in mm
        assert "\\" not in mm["MyModule"]
        assert not mm["MyModule"].startswith("/")

    def test_swift_in_registry(self) -> None:
        """Swift analyzer is registered in the default registry."""
        from agent_fox.knowledge.lang.registry import get_default_registry

        registry = get_default_registry()
        assert registry.get_analyzer(".swift") is not None, (
            ".swift extension must be registered in the default registry"
        )

    # ------------------------------------------------------------------
    # Protocol compliance for all new analyzers
    # ------------------------------------------------------------------

    def test_all_new_analyzers_satisfy_protocol(self) -> None:
        """All six new analyzers satisfy the LanguageAnalyzer protocol."""
        from agent_fox.knowledge.lang.base import LanguageAnalyzer
        from agent_fox.knowledge.lang.bash_lang import BashAnalyzer
        from agent_fox.knowledge.lang.html_lang import HtmlAnalyzer
        from agent_fox.knowledge.lang.json_lang import JsonAnalyzer
        from agent_fox.knowledge.lang.css_lang import CssAnalyzer
        from agent_fox.knowledge.lang.regex_lang import RegexAnalyzer
        from agent_fox.knowledge.lang.swift_lang import SwiftAnalyzer

        for AnalyzerCls in [BashAnalyzer, HtmlAnalyzer, JsonAnalyzer, CssAnalyzer, RegexAnalyzer, SwiftAnalyzer]:
            analyzer = AnalyzerCls()
            assert isinstance(analyzer, LanguageAnalyzer), (
                f"{AnalyzerCls.__name__} must implement LanguageAnalyzer protocol"
            )
            assert len(analyzer.language_name) > 0
            assert len(analyzer.file_extensions) > 0
            for ext in analyzer.file_extensions:
                assert ext.startswith("."), f"Extension {ext!r} must start with '.'"
