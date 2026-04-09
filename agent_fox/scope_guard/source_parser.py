"""Parse source files to extract function/method boundaries and body contents.

Uses regex/heuristic-based extraction (not full AST) for Rust, Python,
and TypeScript/JavaScript.

Requirements: 87-REQ-1.2, 87-REQ-2.1, 87-REQ-2.4, 87-REQ-2.E2
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from agent_fox.scope_guard.models import FileChange, FunctionBody, Language
from agent_fox.scope_guard.stub_patterns import detect_language

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language-specific function signature patterns
# ---------------------------------------------------------------------------

# Rust: fn name(...) { ... }
_RUST_FN_RE = re.compile(
    r"^[ \t]*(?:pub(?:\(crate\))?\s+)?(?:async\s+)?fn\s+(\w+)\s*"
    r"(?:<[^>]*>)?\s*\([^)]*\)(?:\s*->\s*[^\{]+?)?\s*\{",
    re.MULTILINE,
)

# Python: def name(...):
_PYTHON_FN_RE = re.compile(
    r"^[ \t]*(?:async\s+)?def\s+(\w+)\s*\([^)]*\)[^:]*:",
    re.MULTILINE,
)

# TypeScript/JavaScript: function name(...) { or const name = (...) => {
_TS_JS_FN_RE = re.compile(
    r"^[ \t]*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*"
    r"(?:<[^>]*>)?\s*\([^)]*\)[^{]*\{"
    r"|^[ \t]*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*"
    r"(?:async\s+)?\([^)]*\)\s*(?::\s*[^=]*?)?\s*=>\s*\{",
    re.MULTILINE,
)

_FN_PATTERNS: dict[Language, re.Pattern[str]] = {
    Language.RUST: _RUST_FN_RE,
    Language.PYTHON: _PYTHON_FN_RE,
    Language.TYPESCRIPT: _TS_JS_FN_RE,
    Language.JAVASCRIPT: _TS_JS_FN_RE,
}


# ---------------------------------------------------------------------------
# Brace-delimited body extraction (Rust, TS, JS)
# ---------------------------------------------------------------------------


def _extract_brace_body(
    source: str, open_brace_pos: int
) -> tuple[str, int, int] | None:
    """Extract the body between matched braces starting at *open_brace_pos*.

    Returns ``(body_text, start_line, end_line)`` or ``None`` when braces
    are unbalanced.  Lines are 1-indexed.
    """
    depth = 0
    i = open_brace_pos
    length = len(source)
    while i < length:
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                body = source[open_brace_pos + 1 : i]
                start_line = source[:open_brace_pos].count("\n") + 1
                end_line = source[: i + 1].count("\n") + 1
                return body, start_line, end_line
        elif ch == '"':
            i += 1
            while i < length and source[i] != '"':
                if source[i] == "\\":
                    i += 1
                i += 1
        elif ch == "'":
            i += 1
            while i < length and source[i] != "'":
                if source[i] == "\\":
                    i += 1
                i += 1
        i += 1
    return None


# ---------------------------------------------------------------------------
# Indentation-delimited body extraction (Python)
# ---------------------------------------------------------------------------


def _extract_python_body(
    source: str, colon_pos: int
) -> tuple[str, int, int] | None:
    """Extract a Python function body based on indentation after the colon."""
    line_start = source.rfind("\n", 0, colon_pos) + 1
    def_indent = len(source[line_start:]) - len(source[line_start:].lstrip())

    body_start = colon_pos + 1
    newline_pos = source.find("\n", body_start)
    if newline_pos == -1:
        return None

    body_lines: list[str] = []
    pos = newline_pos + 1
    start_line = source[:pos].count("\n") + 1
    end_line = start_line

    while pos < len(source):
        line_end = source.find("\n", pos)
        if line_end == -1:
            line_end = len(source)
        line = source[pos:line_end]

        stripped = line.lstrip()
        if stripped == "":
            body_lines.append(line)
            end_line = source[:line_end].count("\n") + 1
            pos = line_end + 1
            continue

        line_indent = len(line) - len(stripped)
        if line_indent <= def_indent:
            break

        body_lines.append(line)
        end_line = source[:line_end].count("\n") + 1
        pos = line_end + 1

    if not body_lines:
        return None

    body_text = _dedent("\n".join(body_lines))
    return body_text, start_line, end_line


def _dedent(text: str) -> str:
    """Remove common leading whitespace from all non-empty lines."""
    lines = text.split("\n")
    non_empty = [ln for ln in lines if ln.strip()]
    if not non_empty:
        return text
    min_indent = min(len(ln) - len(ln.lstrip()) for ln in non_empty)
    return "\n".join(
        ln[min_indent:] if len(ln) >= min_indent else ln for ln in lines
    )


# ---------------------------------------------------------------------------
# Test-context detection
# ---------------------------------------------------------------------------


def _is_inside_rust_test_block(source: str, pos: int) -> bool:
    """Check if *pos* is inside a ``#[cfg(test)]`` module in Rust."""
    for m in re.finditer(r"#\[cfg\(test\)\]", source):
        if m.start() > pos:
            continue
        brace_pos = source.find("{", m.end())
        if brace_pos == -1:
            continue
        # Walk to find the matching closing brace
        depth = 0
        i = brace_pos
        body_end = brace_pos
        while i < len(source):
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    body_end = i
                    break
            i += 1
        if brace_pos <= pos <= body_end:
            return True
    return False


def _is_function_in_test_context(
    source: str,
    fn_pos: int,
    fn_name: str,
    file_path: str,
    language: Language,
) -> bool:
    """Determine if a function at *fn_pos* is in a test context."""
    if language == Language.RUST:
        preceding = source[max(0, fn_pos - 200) : fn_pos]
        if "#[test]" in preceding:
            return True
        return _is_inside_rust_test_block(source, fn_pos)

    if language == Language.PYTHON:
        basename = os.path.basename(file_path)
        if basename.startswith("test_") or basename.endswith("_test.py"):
            return True
        if fn_name.startswith("test_"):
            return True
        return False

    if language in (Language.TYPESCRIPT, Language.JAVASCRIPT):
        basename = os.path.basename(file_path)
        test_pats = [
            ".test.ts", ".spec.ts", ".test.js", ".spec.js",
            ".test.tsx", ".spec.tsx", ".test.jsx", ".spec.jsx",
        ]
        return any(basename.endswith(p) for p in test_pats)

    return False


# ---------------------------------------------------------------------------
# Shared extraction logic
# ---------------------------------------------------------------------------


def _extract_functions_from_source(
    source: str,
    file_path_str: str,
    language: Language,
    *,
    target_fn: str | None = None,
) -> list[FunctionBody]:
    """Core extraction logic used by all public functions.

    When *target_fn* is given, returns at most one match for that function.
    """
    pattern = _FN_PATTERNS.get(language)
    if pattern is None:
        return []

    results: list[FunctionBody] = []

    for match in pattern.finditer(source):
        fn_name = match.group(1)
        if fn_name is None and match.lastindex and match.lastindex >= 2:
            fn_name = match.group(2)
        if fn_name is None:
            continue

        # If looking for a specific function, filter by name
        if target_fn is not None:
            target_simple = target_fn.rsplit("::", 1)[-1]
            target_simple = target_simple.rsplit(".", 1)[-1]
            if fn_name != target_simple:
                continue

        if language == Language.PYTHON:
            colon_pos = match.end() - 1
            body_result = _extract_python_body(source, colon_pos)
        else:
            brace_pos = source.find("{", match.start())
            if brace_pos == -1:
                continue
            body_result = _extract_brace_body(source, brace_pos)

        if body_result is None:
            continue

        body_text, start_line, end_line = body_result
        in_test = _is_function_in_test_context(
            source, match.start(), fn_name, file_path_str, language
        )
        fb = FunctionBody(
            function_id=fn_name,
            file_path=file_path_str,
            body_text=body_text.strip(),
            language=language,
            start_line=start_line,
            end_line=end_line,
            inside_test_block=in_test,
        )
        if target_fn is not None:
            return [fb]
        results.append(fb)

    return results


def _read_source(file_path: Path) -> str | None:
    """Read source file, returning ``None`` on error."""
    if not file_path.exists():
        return None
    try:
        return file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("Could not read file: %s", file_path)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_function_body(
    file_path: Path, function_id: str
) -> FunctionBody | None:
    """Parse source file, locate function by ID, extract body text and metadata.

    Returns ``None`` if the file doesn't exist, can't be read, or the
    function is not found.
    """
    source = _read_source(file_path)
    if source is None:
        return None

    language = detect_language(str(file_path))
    if language == Language.UNKNOWN:
        logger.warning("Unsupported language for file: %s", file_path)
        return None

    matches = _extract_functions_from_source(
        source, str(file_path), language, target_fn=function_id
    )
    return matches[0] if matches else None


def extract_all_functions(file_path: Path) -> list[FunctionBody]:
    """Extract all functions from a source file."""
    source = _read_source(file_path)
    if source is None:
        return []

    language = detect_language(str(file_path))
    if language == Language.UNKNOWN:
        logger.warning("Unsupported language for file: %s", file_path)
        return []

    return _extract_functions_from_source(source, str(file_path), language)


def extract_modified_functions(file_change: FileChange) -> list[FunctionBody]:
    """Parse diff text to identify and extract function bodies.

    The *diff_text* on ``FileChange`` is expected to contain complete
    function definitions (not unified-diff hunks).
    """
    language = file_change.language
    if language == Language.UNKNOWN:
        return []

    return _extract_functions_from_source(
        file_change.diff_text, file_change.file_path, language
    )
