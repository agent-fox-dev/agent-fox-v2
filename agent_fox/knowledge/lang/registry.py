"""Language registry, file scanning, and language detection.

Requirements: 102-REQ-1.2, 102-REQ-1.3, 102-REQ-1.4, 102-REQ-1.E1, 102-REQ-1.E2
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent_fox.knowledge.lang.base import LanguageAnalyzer

logger = logging.getLogger(__name__)

# Directories excluded during non-gitignore fallback scan.
_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        "vendor",
        "target",
        "build",
        "dist",
        ".venv",
        "venv",
        "env",
        ".env",
        ".tox",
    }
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class LanguageRegistry:
    """Maps file extensions to LanguageAnalyzer instances.

    Requirements: 102-REQ-1.2
    """

    def __init__(self) -> None:
        self._ext_map: dict[str, LanguageAnalyzer] = {}
        self._analyzers: list[LanguageAnalyzer] = []

    def register(self, analyzer: LanguageAnalyzer) -> None:
        """Register an analyzer for its declared file extensions.

        Raises:
            ValueError: If any extension is already claimed by another analyzer.
        """
        for ext in analyzer.file_extensions:
            existing = self._ext_map.get(ext)
            if existing is not None:
                raise ValueError(f"Extension {ext!r} is already registered by the {existing.language_name!r} analyzer")
        # All extensions are free — commit the registration.
        for ext in analyzer.file_extensions:
            self._ext_map[ext] = analyzer
        if analyzer not in self._analyzers:
            self._analyzers.append(analyzer)

    def get_analyzer(self, extension: str) -> LanguageAnalyzer | None:
        """Return the analyzer registered for *extension*, or None."""
        return self._ext_map.get(extension)

    def all_analyzers(self) -> list[LanguageAnalyzer]:
        """Return all registered analyzers in registration order."""
        return list(self._analyzers)


# ---------------------------------------------------------------------------
# File scanning
# ---------------------------------------------------------------------------


def _scan_files(repo_root: Path, extensions: set[str]) -> list[Path]:
    """Return all files under repo_root whose suffix is in *extensions*.

    - Respects .gitignore via the pathspec library when available.
    - Falls back to recursive directory walk excluding common non-source
      directories when no .gitignore is present or pathspec is unavailable.
    - Returned paths are absolute and sorted alphabetically.

    Requirements: 102-REQ-1.4, 102-REQ-1.E2
    """
    spec = _load_gitignore_spec(repo_root)

    found: list[Path] = []
    for file_path in repo_root.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix not in extensions:
            continue

        rel_parts = file_path.relative_to(repo_root).parts

        # Always exclude the explicitly excluded directory names.
        if any(part in _EXCLUDED_DIRS for part in rel_parts[:-1]):
            continue

        # Check .gitignore when spec is available.
        if spec is not None:
            rel_posix = "/".join(rel_parts)
            if spec.match_file(rel_posix):
                continue

        found.append(file_path)

    return sorted(found)


def _load_gitignore_spec(repo_root: Path):  # type: ignore[return]
    """Load .gitignore patterns from repo_root/.gitignore.

    Returns a pathspec.PathSpec instance, or None if unavailable.
    """
    gitignore = repo_root / ".gitignore"
    if not gitignore.is_file():
        return None
    try:
        import pathspec  # type: ignore[import]

        return pathspec.PathSpec.from_lines("gitignore", gitignore.read_text().splitlines())
    except ImportError:
        logger.warning("pathspec library not available; .gitignore patterns will not be applied")
        return None


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------


def detect_languages(repo_root: Path) -> list[LanguageAnalyzer]:
    """Return the subset of registered analyzers that have matching files in repo_root.

    Builds a fresh registry on each call so that grammar availability is
    checked at call time. This allows tests to mock grammar imports and have
    the mock take effect during detection (TS-102-E2).

    Requirements: 102-REQ-1.3
    """
    registry = _build_default_registry()
    detected: list[LanguageAnalyzer] = []
    for analyzer in registry.all_analyzers():
        files = _scan_files(repo_root, analyzer.file_extensions)
        if files:
            detected.append(analyzer)
    return detected


# ---------------------------------------------------------------------------
# Default registry (singleton)
# ---------------------------------------------------------------------------

_default_registry: LanguageRegistry | None = None


def get_default_registry() -> LanguageRegistry:
    """Return the process-wide default language registry.

    The registry is built lazily on first access. Analyzers are only
    registered if their tree-sitter grammar package is installed.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = _build_default_registry()
    return _default_registry


def _try_register(registry: LanguageRegistry, make_fn, name: str) -> None:
    """Try to instantiate and register *make_fn()*, skipping on any failure.

    Verifies that make_parser() succeeds before registering, ensuring that
    analyzers whose grammar packages are not installed are skipped gracefully.

    Requirements: 102-REQ-2.E2
    """
    try:
        analyzer = make_fn()
        analyzer.make_parser()  # Verify the grammar package is available.
        registry.register(analyzer)
    except Exception as exc:  # noqa: BLE001
        logger.info("Skipping %s analyzer: grammar package unavailable (%s)", name, exc)


def _build_default_registry() -> LanguageRegistry:
    """Construct the default registry with all available language analyzers."""
    registry = LanguageRegistry()

    # Python — always available (tree-sitter-python is a core dependency).
    from agent_fox.knowledge.lang.python_lang import PythonAnalyzer

    _try_register(registry, PythonAnalyzer, "python")

    # Go
    try:
        from agent_fox.knowledge.lang.go_lang import GoAnalyzer

        _try_register(registry, GoAnalyzer, "go")
    except ImportError:
        logger.info("Skipping go analyzer: go_lang module not available")

    # Rust
    try:
        from agent_fox.knowledge.lang.rust_lang import RustAnalyzer

        _try_register(registry, RustAnalyzer, "rust")
    except ImportError:
        logger.info("Skipping rust analyzer: rust_lang module not available")

    # TypeScript and JavaScript
    try:
        from agent_fox.knowledge.lang.typescript_lang import JavaScriptAnalyzer, TypeScriptAnalyzer

        _try_register(registry, TypeScriptAnalyzer, "typescript")
        _try_register(registry, JavaScriptAnalyzer, "javascript")
    except ImportError:
        logger.info("Skipping typescript/javascript analyzers: typescript_lang module not available")

    # Java
    try:
        from agent_fox.knowledge.lang.java_lang import JavaAnalyzer

        _try_register(registry, JavaAnalyzer, "java")
    except ImportError:
        logger.info("Skipping java analyzer: java_lang module not available")

    # C and C++
    try:
        from agent_fox.knowledge.lang.c_lang import CAnalyzer, CppAnalyzer

        _try_register(registry, CAnalyzer, "c")
        _try_register(registry, CppAnalyzer, "cpp")
    except ImportError:
        logger.info("Skipping c/cpp analyzers: c_lang module not available")

    # Ruby
    try:
        from agent_fox.knowledge.lang.ruby_lang import RubyAnalyzer

        _try_register(registry, RubyAnalyzer, "ruby")
    except ImportError:
        logger.info("Skipping ruby analyzer: ruby_lang module not available")

    # C#
    try:
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        _try_register(registry, CSharpAnalyzer, "csharp")
    except ImportError:
        logger.info("Skipping csharp analyzer: csharp_lang module not available")

    # Elixir
    try:
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        _try_register(registry, ElixirAnalyzer, "elixir")
    except ImportError:
        logger.info("Skipping elixir analyzer: elixir_lang module not available")

    # Kotlin
    try:
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        _try_register(registry, KotlinAnalyzer, "kotlin")
    except ImportError:
        logger.info("Skipping kotlin analyzer: kotlin_lang module not available")

    # Dart
    try:
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        _try_register(registry, DartAnalyzer, "dart")
    except ImportError:
        logger.info("Skipping dart analyzer: dart_lang module not available")

    # Bash
    try:
        from agent_fox.knowledge.lang.bash_lang import BashAnalyzer

        _try_register(registry, BashAnalyzer, "bash")
    except ImportError:
        logger.info("Skipping bash analyzer: bash_lang module not available")

    # HTML
    try:
        from agent_fox.knowledge.lang.html_lang import HtmlAnalyzer

        _try_register(registry, HtmlAnalyzer, "html")
    except ImportError:
        logger.info("Skipping html analyzer: html_lang module not available")

    # JSON
    try:
        from agent_fox.knowledge.lang.json_lang import JsonAnalyzer

        _try_register(registry, JsonAnalyzer, "json")
    except ImportError:
        logger.info("Skipping json analyzer: json_lang module not available")

    # CSS
    try:
        from agent_fox.knowledge.lang.css_lang import CssAnalyzer

        _try_register(registry, CssAnalyzer, "css")
    except ImportError:
        logger.info("Skipping css analyzer: css_lang module not available")

    # Regex
    try:
        from agent_fox.knowledge.lang.regex_lang import RegexAnalyzer

        _try_register(registry, RegexAnalyzer, "regex")
    except ImportError:
        logger.info("Skipping regex analyzer: regex_lang module not available")

    # Swift
    try:
        from agent_fox.knowledge.lang.swift_lang import SwiftAnalyzer

        _try_register(registry, SwiftAnalyzer, "swift")
    except ImportError:
        logger.info("Skipping swift analyzer: swift_lang module not available")

    return registry
