"""Validation utilities for LLM JSON responses.

Enforces field-level constraints (max string length) to prevent memory
exhaustion and persistent prompt injection from malformed or manipulated
LLM output.

Requirements: Issue #186 — F5 unsafe deserialization mitigation.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("agent_fox.core.llm_validation")

# ---------------------------------------------------------------------------
# Size and length limits
# ---------------------------------------------------------------------------

MAX_RAW_RESPONSE_BYTES = 500_000  # 500 KB — reject before JSON parsing
MAX_CONTENT_LENGTH = 5_000  # Fact content / finding description
MAX_KEYWORD_LENGTH = 100  # Single keyword
MAX_KEYWORDS = 20  # Keywords per fact
MAX_REF_LENGTH = 500  # requirement_ref, spec_ref, artifact_ref
MAX_EVIDENCE_LENGTH = 10_000  # Verification evidence


def truncate_field(value: str, *, max_length: int, field_name: str) -> str:
    """Truncate a string field to *max_length* characters.

    Logs a warning when truncation occurs so callers can audit
    excessively large LLM outputs.
    """
    if len(value) <= max_length:
        return value
    logger.warning(
        "Truncating %s from %d to %d chars",
        field_name,
        len(value),
        max_length,
    )
    return value[:max_length]
