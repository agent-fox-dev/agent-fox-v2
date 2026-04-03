"""Validation utilities for LLM JSON responses.

Enforces field-level constraints (max string length, max keyword count)
and raw response size limits to prevent memory exhaustion and persistent
prompt injection from malformed or manipulated LLM output.

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


class ResponseTooLargeError(Exception):
    """Raised when a raw LLM response exceeds the size threshold."""


def check_response_size(
    text: str,
    *,
    max_bytes: int = MAX_RAW_RESPONSE_BYTES,
    context: str = "LLM response",
) -> None:
    """Reject a raw response that exceeds the byte-size threshold.

    Raises ResponseTooLargeError if the UTF-8 encoded text exceeds
    *max_bytes*. Called before ``json.loads()`` to prevent memory
    exhaustion from oversized payloads.
    """
    size = len(text.encode("utf-8", errors="replace"))
    if size > max_bytes:
        raise ResponseTooLargeError(f"{context} is {size:,} bytes, exceeding the {max_bytes:,}-byte limit")


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


def validate_keywords(
    keywords: list,
    *,
    max_count: int = MAX_KEYWORDS,
    max_length: int = MAX_KEYWORD_LENGTH,
) -> list[str]:
    """Validate and sanitize a keyword list.

    - Non-string items are dropped.
    - Individual keywords are truncated to *max_length*.
    - The list is capped at *max_count* items.
    """
    result: list[str] = []
    for kw in keywords:
        if not isinstance(kw, str):
            continue
        result.append(kw[:max_length])
        if len(result) >= max_count:
            break
    return result
