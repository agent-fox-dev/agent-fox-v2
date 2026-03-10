"""File outline tool using heuristic regex-based parsing.

Detects structural declarations (functions, classes, constants, imports)
across multiple languages without requiring AST or tree-sitter.

Requirements: 29-REQ-1.1, 29-REQ-1.2, 29-REQ-1.3, 29-REQ-1.4,
              29-REQ-1.E1, 29-REQ-1.E2, 29-REQ-1.E3
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.tools.types import OutlineResult, Symbol

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
}

# ---------------------------------------------------------------------------
# Per-language regex patterns
#
# Each pattern is a tuple of (compiled_regex, kind_string, name_group_index).
# The name_group_index indicates which capture group holds the symbol name.
# ---------------------------------------------------------------------------

_IMPORT_PATTERNS: dict[str, re.Pattern[str]] = {
    "python": re.compile(r"^(import\s|from\s+\S+\s+import\s)"),
    "javascript": re.compile(r"^import\s"),
    "typescript": re.compile(r"^import\s"),
    "rust": re.compile(r"^use\s"),
    "go": re.compile(r"^import\s"),
    "java": re.compile(r"^import\s"),
}

# Declaration patterns: list of (regex, kind, name_group)
_DECLARATION_PATTERNS: dict[str, list[tuple[re.Pattern[str], str, int]]] = {
    "python": [
        (re.compile(r"^class\s+(\w+)"), "class", 1),
        (re.compile(r"^(?:async\s+)?def\s+(\w+)"), "function", 1),
        (re.compile(r"^([A-Z][A-Z_0-9]+)\s*="), "constant", 1),
    ],
    "javascript": [
        (re.compile(r"^(?:export\s+)?class\s+(\w+)"), "class", 1),
        (re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)"), "function", 1),
        (
            re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(\w+)"),
            "constant",
            1,
        ),
    ],
    "typescript": [
        (re.compile(r"^(?:export\s+)?class\s+(\w+)"), "class", 1),
        (re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)"), "function", 1),
        (
            re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(\w+)"),
            "constant",
            1,
        ),
    ],
    "rust": [
        (re.compile(r"^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)"), "function", 1),
        (re.compile(r"^(?:pub\s+)?struct\s+(\w+)"), "class", 1),
        (re.compile(r"^(?:pub\s+)?enum\s+(\w+)"), "class", 1),
        (re.compile(r"^(?:pub\s+)?trait\s+(\w+)"), "class", 1),
        (re.compile(r"^impl\s+(\w+)"), "class", 1),
        (re.compile(r"^(?:pub\s+)?mod\s+(\w+)"), "class", 1),
        (re.compile(r"^(?:pub\s+)?const\s+(\w+)"), "constant", 1),
    ],
    "go": [
        (re.compile(r"^func\s+\(\w+\s+\*?(\w+)\)\s+(\w+)"), "method", 2),
        (re.compile(r"^func\s+(\w+)"), "function", 1),
        (re.compile(r"^type\s+(\w+)"), "class", 1),
    ],
    "java": [
        (
            re.compile(
                r"^(?:public|private|protected)?\s*(?:static\s+)?(?:class|interface)\s+(\w+)"
            ),
            "class",
            1,
        ),
        (re.compile(r"^enum\s+(\w+)"), "class", 1),
    ],
}

# Fallback patterns for unknown file extensions
_FALLBACK_PATTERNS: list[tuple[re.Pattern[str], str, int]] = [
    (re.compile(r"^(?:export\s+)?class\s+(\w+)"), "class", 1),
    (
        re.compile(r"^(?:export\s+)?(?:async\s+)?(?:def|function)\s+(\w+)"),
        "function",
        1,
    ),
]

_FALLBACK_IMPORT = re.compile(r"^(?:import\s|from\s+\S+\s+import\s|use\s)")


# ---------------------------------------------------------------------------
# End-line detection
# ---------------------------------------------------------------------------


def _detect_end_line_python(lines: list[str], start_idx: int, start_indent: int) -> int:
    """Detect end line for a Python declaration using indentation."""
    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        stripped = line.rstrip()
        if not stripped:
            continue  # skip blank lines
        indent = len(line) - len(line.lstrip())
        if indent <= start_indent and stripped:
            return i  # 0-based index of the NEXT declaration
    return len(lines)  # extends to EOF


def _detect_end_line_brace(lines: list[str], start_idx: int, _start_indent: int) -> int:
    """Detect end line for brace languages by tracking brace depth."""
    depth = 0
    found_open = False
    for i in range(start_idx, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
                found_open = True
            elif ch == "}":
                depth -= 1
                if found_open and depth <= 0:
                    return i + 1  # 0-based exclusive end
    return len(lines)


def _detect_end_line_fallback(
    lines: list[str], start_idx: int, _start_indent: int, next_start: int | None
) -> int:
    """Fallback: next declaration start - 1, or EOF."""
    if next_start is not None:
        return next_start
    return len(lines)


# ---------------------------------------------------------------------------
# Core outline function
# ---------------------------------------------------------------------------


def _is_binary(data: bytes) -> bool:
    """Check if data contains null bytes in the first 8192 bytes."""
    return b"\x00" in data[:8192]


def _parse_symbols(lines: list[str], language: str) -> list[Symbol]:
    """Parse symbols from file lines using language-specific patterns."""
    patterns = _DECLARATION_PATTERNS.get(language, _FALLBACK_PATTERNS)
    import_pattern = _IMPORT_PATTERNS.get(language, _FALLBACK_IMPORT)

    use_python_end = language == "python"
    use_brace_end = language in ("javascript", "typescript", "rust", "go", "java")

    # First pass: find all declaration start lines and import lines
    raw_symbols: list[tuple[int, str, str]] = []  # (0-based idx, kind, name)
    import_lines: list[int] = []  # 0-based indices

    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped:
            continue

        # Check for imports first
        if import_pattern.search(stripped):
            import_lines.append(idx)
            continue

        # Check declaration patterns
        for regex, kind, name_group in patterns:
            m = regex.search(stripped)
            if m:
                raw_symbols.append((idx, kind, m.group(name_group)))
                break

    # Build symbols with end-line detection
    symbols: list[Symbol] = []

    # Collapse contiguous import lines into blocks
    if import_lines:
        blocks = _collapse_import_lines(import_lines)
        for block_start, block_end in blocks:
            count = block_end - block_start + 1
            symbols.append(
                Symbol(
                    kind="import_block",
                    name=f"({count} imports)" if count > 1 else "(1 import)",
                    start_line=block_start + 1,  # 1-based
                    end_line=block_end + 1,  # 1-based
                )
            )

    # Process declaration symbols with end-line detection
    for i, (idx, kind, name) in enumerate(raw_symbols):
        start_indent = len(lines[idx]) - len(lines[idx].lstrip())
        next_start = raw_symbols[i + 1][0] if i + 1 < len(raw_symbols) else None

        if use_python_end:
            end_idx = _detect_end_line_python(lines, idx, start_indent)
            # end_idx is exclusive (next decl or EOF)
            end_line = end_idx  # 0-based exclusive -> last line index
        elif use_brace_end:
            end_idx = _detect_end_line_brace(lines, idx, start_indent)
            end_line = end_idx  # 0-based exclusive
        else:
            end_idx = _detect_end_line_fallback(lines, idx, start_indent, next_start)
            end_line = end_idx

        # Convert to 1-based inclusive
        start_1 = idx + 1
        end_1 = max(end_line, idx + 1)  # at least the declaration line

        symbols.append(Symbol(kind=kind, name=name, start_line=start_1, end_line=end_1))

    # Sort by start_line
    symbols.sort(key=lambda s: s.start_line)

    return symbols


def _collapse_import_lines(indices: list[int]) -> list[tuple[int, int]]:
    """Collapse contiguous 0-based line indices into (start, end) blocks."""
    if not indices:
        return []

    blocks: list[tuple[int, int]] = []
    block_start = indices[0]
    prev = indices[0]

    for idx in indices[1:]:
        if idx == prev + 1:
            prev = idx
        else:
            blocks.append((block_start, prev))
            block_start = idx
            prev = idx

    blocks.append((block_start, prev))
    return blocks


def fox_outline(file_path: str) -> OutlineResult | str:
    """Return structural outline of a file.

    Returns an OutlineResult on success, or an error string on failure.
    """
    path = Path(file_path)

    # Check existence
    if not path.exists():
        return f"Error: file not found: {file_path}"

    if not path.is_file():
        return f"Error: not a file: {file_path}"

    # Read raw bytes for binary detection
    try:
        raw = path.read_bytes()
    except OSError as e:
        return f"Error: cannot read {file_path}: {e}"

    # Binary check
    if _is_binary(raw):
        return f"Error: {file_path} appears to be a binary file, not a text file"

    # Empty file
    if not raw:
        return OutlineResult(symbols=[], total_lines=0)

    # Decode
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except UnicodeDecodeError:
            return f"Error: cannot decode {file_path} as text"

    lines = text.splitlines(keepends=True)
    total_lines = len(lines)

    # Detect language
    ext = path.suffix.lower()
    language = _EXTENSION_MAP.get(ext, "unknown")

    # Parse symbols
    symbols = _parse_symbols(lines, language)

    return OutlineResult(symbols=symbols, total_lines=total_lines)
