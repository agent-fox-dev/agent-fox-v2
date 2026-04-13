"""Shared helpers, constants, and regex patterns for validation rules."""

from __future__ import annotations

import re

from agent_fox.spec._patterns import (
    H2_HEADING as _H2_HEADING,
)
from agent_fox.spec._patterns import (
    extract_req_ids_from_text as _extract_req_ids_from_text,
)
from agent_fox.spec._patterns import (
    normalize_heading as _normalize_heading,
)

# -- Severity constants -------------------------------------------------------

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_HINT = "hint"

# Sorting order: error < warning < hint
SEVERITY_ORDER = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_HINT: 2}

# -- Constants -----------------------------------------------------------------

EXPECTED_FILES = ["prd.md", "requirements.md", "design.md", "test_spec.md", "tasks.md"]
MAX_SUBTASKS_PER_GROUP = 6
MAX_REQUIREMENTS = 10

# Regex patterns for parsing
_REQUIREMENT_HEADING = re.compile(r"^###\s+Requirement\s+(\d+):\s*(.+)$")
_REQUIREMENT_ID = re.compile(r"(?:\[|\*\*)(\d{2}-REQ-\d+\.\d+)(?:\]|[:\*])")
_GROUP_REF = re.compile(r"\bgroup\s+(\d+)\b", re.IGNORECASE)

# EARS keyword detection -- all EARS patterns include SHALL
_EARS_KEYWORD = re.compile(r"\bSHALL\b")

# Requirement ID format variants (for inconsistency detection)
_REQ_ID_BRACKET = re.compile(r"\[(\d{2}-REQ-\d+\.(?:\d+|E\d+))\]")
_REQ_ID_BOLD = re.compile(r"\*\*(\d{2}-REQ-\d+\.(?:\d+|E\d+))[:\*]")

# Design document section patterns
_PROPERTY_HEADING = re.compile(r"^###\s+Property\s+\d+", re.IGNORECASE)

_TS_REFERENCE = re.compile(r"TS-\d{2}-(?:P|E)?\d+")

# Markdown table row detection
_TABLE_PIPE_ROW = re.compile(r"^\s*\|.+\|")
_TABLE_SEP_ROW = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")

# -- Section schema definitions (Phase 4) -------------------------------------
# Maps file -> list of (section_name, required). "required" means warning if
# missing; non-required means hint.

_SECTION_SCHEMAS: dict[str, list[tuple[str, bool]]] = {
    "requirements.md": [
        ("Introduction", True),
        ("Glossary", True),
        ("Requirements", True),
    ],
    "design.md": [
        ("Overview", True),
        ("Architecture", True),
        ("Components and Interfaces", False),
        ("Data Models", False),
        ("Operational Readiness", False),
        ("Correctness Properties", True),
        ("Error Handling", True),
        ("Execution Paths", True),
        ("Technology Stack", False),
        ("Definition of Done", True),
        ("Testing Strategy", False),
    ],
    "test_spec.md": [
        ("Overview", False),
        ("Test Cases", True),
        ("Edge Case Tests", False),
        ("Integration Smoke Tests", True),
        ("Property Test Cases", False),
        ("Coverage Matrix", True),
    ],
    "tasks.md": [
        ("Overview", False),
        ("Test Commands", False),
        ("Tasks", True),
        ("Traceability", False),
        ("Notes", False),
    ],
}


def _spec_prefix(spec_name: str) -> str | None:
    """Extract the two-digit numeric prefix from a spec name (e.g. '28').

    Returns None if the name doesn't start with a two-digit prefix,
    which disables prefix-based filtering.
    """
    m = re.match(r"(\d{2})_", spec_name)
    return m.group(1) if m else None


# Re-export imported helpers so other sub-modules can use them via _helpers.
__all__ = [
    "EXPECTED_FILES",
    "MAX_REQUIREMENTS",
    "MAX_SUBTASKS_PER_GROUP",
    "SEVERITY_ERROR",
    "SEVERITY_HINT",
    "SEVERITY_ORDER",
    "SEVERITY_WARNING",
    "_EARS_KEYWORD",
    "_GROUP_REF",
    "_H2_HEADING",
    "_PROPERTY_HEADING",
    "_REQ_ID_BOLD",
    "_REQ_ID_BRACKET",
    "_REQUIREMENT_HEADING",
    "_REQUIREMENT_ID",
    "_SECTION_SCHEMAS",
    "_TABLE_PIPE_ROW",
    "_TABLE_SEP_ROW",
    "_TS_REFERENCE",
    "_extract_req_ids_from_text",
    "_normalize_heading",
    "_spec_prefix",
]
