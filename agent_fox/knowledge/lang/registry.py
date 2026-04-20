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


_ANALYZER_SPECS: list[tuple[str, str, str]] = [
    ("agent_fox.knowledge.lang.python_lang", "PythonAnalyzer", "python"),
    ("agent_fox.knowledge.lang.go_lang", "GoAnalyzer", "go"),
    ("agent_fox.knowledge.lang.rust_lang", "RustAnalyzer", "rust"),
    ("agent_fox.knowledge.lang.typescript_lang", "TypeScriptAnalyzer", "typescript"),
    ("agent_fox.knowledge.lang.typescript_lang", "JavaScriptAnalyzer", "javascript"),
    ("agent_fox.knowledge.lang.java_lang", "JavaAnalyzer", "java"),
    ("agent_fox.knowledge.lang.c_lang", "CAnalyzer", "c"),
    ("agent_fox.knowledge.lang.c_lang", "CppAnalyzer", "cpp"),
    ("agent_fox.knowledge.lang.ruby_lang", "RubyAnalyzer", "ruby"),
    ("agent_fox.knowledge.lang.csharp_lang", "CSharpAnalyzer", "csharp"),
    ("agent_fox.knowledge.lang.elixir_lang", "ElixirAnalyzer", "elixir"),
    ("agent_fox.knowledge.lang.kotlin_lang", "KotlinAnalyzer", "kotlin"),
    ("agent_fox.knowledge.lang.dart_lang", "DartAnalyzer", "dart"),
    ("agent_fox.knowledge.lang.bash_lang", "BashAnalyzer", "bash"),
    ("agent_fox.knowledge.lang.simple_lang", "HtmlAnalyzer", "html"),
    ("agent_fox.knowledge.lang.simple_lang", "JsonAnalyzer", "json"),
    ("agent_fox.knowledge.lang.css_lang", "CssAnalyzer", "css"),
    ("agent_fox.knowledge.lang.simple_lang", "RegexAnalyzer", "regex"),
    ("agent_fox.knowledge.lang.swift_lang", "SwiftAnalyzer", "swift"),
]


def _build_default_registry() -> LanguageRegistry:
    """Construct the default registry with all available language analyzers."""
    import importlib

    registry = LanguageRegistry()
    for module_path, class_name, display_name in _ANALYZER_SPECS:
        try:
            mod = importlib.import_module(module_path)
            analyzer_cls = getattr(mod, class_name)
            _try_register(registry, analyzer_cls, display_name)
        except (ImportError, AttributeError):
            logger.info("Skipping %s analyzer: module not available", display_name)
    return registry
