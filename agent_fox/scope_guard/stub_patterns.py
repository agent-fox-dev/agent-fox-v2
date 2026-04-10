"""Language-specific stub placeholder patterns and test-block detection rules.

Requirements: 87-REQ-1.4, 87-REQ-1.E1, 87-REQ-1.E2
"""

from __future__ import annotations

import re

from agent_fox.scope_guard.models import Language

# ---------------------------------------------------------------------------
# File-extension → Language mapping
# ---------------------------------------------------------------------------

_EXTENSION_MAP: dict[str, Language] = {
    ".rs": Language.RUST,
    ".py": Language.PYTHON,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".cjs": Language.JAVASCRIPT,
}

# ---------------------------------------------------------------------------
# Stub patterns per language
#
# A body is a stub iff, after stripping comments and whitespace, its entire
# content matches exactly ONE of these patterns — no additional statements.
# ---------------------------------------------------------------------------

_RUST_STUB_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^todo!\(\s*\)$"),
    re.compile(r'^todo!\(\s*"[^"]*"\s*\)$'),
    re.compile(r"^unimplemented!\(\s*\)$"),
    re.compile(r'^unimplemented!\(\s*"[^"]*"\s*\)$'),
    re.compile(r'^panic!\(\s*"[^"]*"\s*\)$'),
]

_PYTHON_STUB_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^raise\s+NotImplementedError$"),
    re.compile(r'^raise\s+NotImplementedError\(\s*"[^"]*"\s*\)$'),
    re.compile(r"^raise\s+NotImplementedError\(\s*\)$"),
    re.compile(r"^pass$"),
]

_TS_JS_STUB_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'^throw\s+new\s+Error\(\s*"[^"]*"\s*\)$'),
    re.compile(r"^throw\s+new\s+Error\(\s*\)$"),
    re.compile(r"^throw\s+new\s+Error\(\s*'[^']*'\s*\)$"),
]

_PATTERNS: dict[Language, list[re.Pattern[str]]] = {
    Language.RUST: _RUST_STUB_PATTERNS,
    Language.PYTHON: _PYTHON_STUB_PATTERNS,
    Language.TYPESCRIPT: _TS_JS_STUB_PATTERNS,
    Language.JAVASCRIPT: _TS_JS_STUB_PATTERNS,
}

# ---------------------------------------------------------------------------
# Comment stripping helpers
# ---------------------------------------------------------------------------

# Rust/TS/JS: line comments (//) and block comments (/* ... */)
_C_STYLE_LINE_COMMENT = re.compile(r"//[^\n]*")
_C_STYLE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# Python: line comments (#)
_PYTHON_LINE_COMMENT = re.compile(r"#[^\n]*")

# Python docstrings (triple quotes)
_PYTHON_DOCSTRING = re.compile(r'(""".*?"""|\'\'\'.*?\'\'\')', re.DOTALL)


def _strip_comments(body: str, language: Language) -> str:
    """Remove comments (and Python docstrings) from a body string."""
    if language == Language.PYTHON:
        result = _PYTHON_DOCSTRING.sub("", body)
        result = _PYTHON_LINE_COMMENT.sub("", result)
    else:
        result = _C_STYLE_BLOCK_COMMENT.sub("", body)
        result = _C_STYLE_LINE_COMMENT.sub("", result)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_stub_body(body: str, language: Language) -> bool:
    """Check if a function body is a stub placeholder.

    Returns True iff the body, after stripping comments and whitespace,
    consists entirely of a single recognized stub placeholder for the language.
    Any additional statements disqualify it (87-REQ-1.E2).
    """
    if language == Language.UNKNOWN:
        return False

    patterns = _PATTERNS.get(language)
    if not patterns:
        return False

    stripped = _strip_comments(body, language).strip()
    if not stripped:
        return False

    # Must match exactly one pattern — the entire stripped content
    # with optional trailing semicolons (Rust/TS/JS)
    candidate = stripped.rstrip(";").strip()

    return any(pat.match(candidate) for pat in patterns)


def detect_language(file_path: str) -> Language:
    """Detect programming language from file extension."""
    for ext, lang in _EXTENSION_MAP.items():
        if file_path.endswith(ext):
            return lang
    return Language.UNKNOWN


def get_stub_patterns(language: Language) -> list[re.Pattern[str]]:
    """Return compiled regex patterns for stub placeholders in the given language."""
    return list(_PATTERNS.get(language, []))


def is_test_block(body: str, file_path: str, language: Language) -> bool:
    """Determine if a code block is inside a test-attributed region.

    Detection rules per language (from design.md):
    - Rust: code inside #[cfg(test)] module or #[test] attributed functions
    - Python: files matching test_*.py or *_test.py, or functions/methods
      starting with test_, or code inside classes inheriting from TestCase
    - TypeScript/JS: files matching *.test.ts, *.spec.ts, *.test.js, *.spec.js,
      or code inside describe()/it()/test() blocks
    """
    import os

    basename = os.path.basename(file_path)

    if language == Language.RUST:
        return "#[cfg(test)]" in body or "#[test]" in body

    if language == Language.PYTHON:
        # File-level detection
        if basename.startswith("test_") or basename.endswith("_test.py"):
            return True
        # Function-level: check if body context suggests test
        if "unittest.TestCase" in body or "class Test" in body:
            return True
        return False

    if language in (Language.TYPESCRIPT, Language.JAVASCRIPT):
        # File-level detection
        test_file_patterns = [
            ".test.ts",
            ".spec.ts",
            ".test.js",
            ".spec.js",
            ".test.tsx",
            ".spec.tsx",
            ".test.jsx",
            ".spec.jsx",
        ]
        if any(basename.endswith(p) for p in test_file_patterns):
            return True
        # Block-level detection
        if re.search(r"\b(describe|it|test)\s*\(", body):
            return True
        return False

    return False
