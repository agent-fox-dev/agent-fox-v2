"""Shared data types for spec fixers.

Requirements: 20-REQ-6.*
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# -- Regex patterns for parsing stale-dependency finding messages ---------------

_SUGGESTION_PATTERN = re.compile(r"Suggestion: (.+)$")
_IDENTIFIER_PATTERN = re.compile(r"identifier `([^`]+)`")

# Regex for locating criterion IDs in requirements.md
# Supports bracket format: [99-REQ-1.1] and bold format: **99-REQ-1.1:**
_CRITERION_BRACKET = re.compile(
    r"^(\s*\d+\.\s*)\[({cid})\]\s*(.*)$",
)
_CRITERION_BOLD = re.compile(
    r"^(\s*\d+\.\s*)\*\*({cid}):\*\*\s*(.*)$",
)

_REQ_ID_IN_MESSAGE = re.compile(r"\b(\d+-REQ-\d+\.(?:\d+|E\d+))\b")


@dataclass(frozen=True)
class IdentifierFix:
    """A single identifier correction from AI validation.

    Requirements: 21-REQ-5.1
    """

    original: str  # the stale identifier (e.g., "SnippetStore")
    suggestion: str  # the AI-suggested replacement (e.g., "Store")
    upstream_spec: str  # which upstream spec this relates to


@dataclass(frozen=True)
class FixResult:
    """Result of applying a single fix."""

    rule: str
    spec_name: str
    file: str
    description: str


# Set of rules that have auto-fixers
FIXABLE_RULES = {
    "coarse-dependency",
    "missing-verification",
    "stale-dependency",
    "inconsistent-req-id-format",
    "missing-traceability-table",
    "missing-coverage-matrix",
    "missing-definition-of-done",
    "missing-error-table",
    "missing-correctness-properties",
    "invalid-archetype-tag",
    "malformed-archetype-tag",
    "invalid-checkbox-state",
    "traceability-table-mismatch",
    "coverage-matrix-mismatch",
}

# AI-specific fixable rules (only active when --ai flag is set)
AI_FIXABLE_RULES = {"vague-criterion", "implementation-leak", "untraced-requirement"}
