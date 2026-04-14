"""Shared regex patterns and utility functions for spec validation and fixing.

Extracted from validator.py to eliminate cross-module private symbol imports.
Both validator.py and fixer.py import from here.
"""

from __future__ import annotations

import re
from pathlib import Path

# Section heading (## level)
H2_HEADING = re.compile(r"^##\s+(.+)$")

# Broader pattern to catch malformed archetype tags: matches things like
# [archtype: X], [Archetype: X], [archetype X], [archetype:X], etc.
MALFORMED_ARCHETYPE_TAG = re.compile(r"\[arch[e]?type[:\s]\s*\w+\]", re.IGNORECASE)

# Valid checkbox characters in task group / subtask lines
VALID_CHECKBOX_CHARS = {" ", "x", "-", "~"}

# Matches any checkbox-like pattern at the start of a task line
CHECKBOX_LINE = re.compile(r"^(\s*)- \[(.)\](\s+\*?\s*)(\d+)[\.\s]")

# Test spec entry headings: ### TS-NN-N, ### TS-NN-PN, ### TS-NN-EN
TS_ENTRY_HEADING = re.compile(r"^###\s+(TS-\d+-(?:P|E)?\d+)")

# Permissive requirement ID pattern — matches bare IDs in tables/prose
REQ_ID_BARE = re.compile(r"(\d+-REQ-\d+\.(?:\d+|E\d+))")


def normalize_heading(text: str) -> str:
    """Normalize a heading for fuzzy comparison."""
    return re.sub(r"[\s_\-]+", " ", text.strip().lower())


def extract_test_spec_ids(spec_path: Path) -> set[str]:
    """Extract all TS-NN-N IDs from test_spec.md headings."""
    ts_path = spec_path / "test_spec.md"
    if not ts_path.is_file():
        return set()
    text = ts_path.read_text(encoding="utf-8")
    ids: set[str] = set()
    for line in text.splitlines():
        m = TS_ENTRY_HEADING.match(line)
        if m:
            ids.add(m.group(1))
    return ids


def extract_req_ids_from_text(
    text: str,
    spec_prefix: str | None = None,
) -> set[str]:
    """Extract requirement IDs from arbitrary text.

    Uses a permissive pattern that matches bare IDs (without brackets or bold)
    so it works in tables, prose, and formatted text.

    Args:
        text: The text to scan for requirement IDs.
        spec_prefix: If set (e.g. "28"), only return IDs whose numeric prefix
            matches. This filters out cross-spec references that happen to
            appear in the text.
    """
    ids = set(REQ_ID_BARE.findall(text))
    if spec_prefix is not None:
        ids = {rid for rid in ids if rid.startswith(f"{spec_prefix}-REQ-")}
    return ids
