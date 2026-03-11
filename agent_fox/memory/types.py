"""Data types for the structured memory system.

Defines Fact dataclass, Category enum, confidence parsing utilities,
and the deprecated ConfidenceLevel enum (kept for backward compatibility).

Requirements: 05-REQ-2.1, 05-REQ-3.2, 37-REQ-1.*
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger("agent_fox.memory.types")


class Category(StrEnum):
    """Classification labels for extracted facts."""

    GOTCHA = "gotcha"
    PATTERN = "pattern"
    DECISION = "decision"
    CONVENTION = "convention"
    ANTI_PATTERN = "anti_pattern"
    FRAGILE_AREA = "fragile_area"


class ConfidenceLevel(StrEnum):
    """Reliability level of an extracted fact.

    .. deprecated::
        Kept for backward compatibility. Use :func:`parse_confidence` and
        float confidence values instead.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# -- Confidence normalization ------------------------------------------------
# Requirements: 37-REQ-1.2, 37-REQ-1.3, 37-REQ-1.E1, 37-REQ-1.E2

CONFIDENCE_MAP: dict[str, float] = {
    "high": 0.9,
    "medium": 0.6,
    "low": 0.3,
}

DEFAULT_CONFIDENCE: float = 0.6


def parse_confidence(value: str | float | int | None) -> float:
    """Convert any confidence representation to float [0.0, 1.0].

    - str: look up in CONFIDENCE_MAP, default to 0.6 if unknown
    - float/int: clamp to [0.0, 1.0]
    - None: return DEFAULT_CONFIDENCE

    Args:
        value: A confidence value in any supported format.

    Returns:
        A float in [0.0, 1.0].
    """
    if value is None:
        return DEFAULT_CONFIDENCE

    if isinstance(value, str):
        mapped = CONFIDENCE_MAP.get(value.lower())
        if mapped is not None:
            return mapped
        # Try parsing as a numeric string (e.g. "0.9")
        try:
            numeric = float(value)
            return max(0.0, min(1.0, numeric))
        except (ValueError, OverflowError):
            pass
        logger.warning(
            "Unknown confidence string '%s', defaulting to %.1f",
            value,
            DEFAULT_CONFIDENCE,
        )
        return DEFAULT_CONFIDENCE

    if isinstance(value, (int, float)):
        return float(max(0.0, min(1.0, value)))

    logger.warning(
        "Unexpected confidence type %s, defaulting to %.1f",
        type(value).__name__,
        DEFAULT_CONFIDENCE,
    )
    return DEFAULT_CONFIDENCE


@dataclass
class Fact:
    """A structured unit of knowledge extracted from a coding session."""

    id: str  # UUID v4
    content: str  # Description of the learning
    category: str  # Category enum value
    spec_name: str  # Source specification name
    keywords: list[str]  # Relevant terms for matching
    confidence: float  # [0.0, 1.0] — was: str (37-REQ-1.4)
    created_at: str  # ISO 8601 timestamp
    supersedes: str | None = None  # UUID of the fact this one replaces
    session_id: str | None = None  # Node ID of the session that produced this fact
    commit_sha: str | None = None  # Git commit SHA associated with this fact
