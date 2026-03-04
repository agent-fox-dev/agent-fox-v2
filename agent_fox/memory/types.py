"""Data types for the structured memory system.

Defines Fact dataclass, Category enum, and ConfidenceLevel enum.

Requirements: 05-REQ-2.1, 05-REQ-3.2
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Category(StrEnum):
    """Classification labels for extracted facts."""

    GOTCHA = "gotcha"
    PATTERN = "pattern"
    DECISION = "decision"
    CONVENTION = "convention"
    ANTI_PATTERN = "anti_pattern"
    FRAGILE_AREA = "fragile_area"


class ConfidenceLevel(StrEnum):
    """Reliability level of an extracted fact."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Fact:
    """A structured unit of knowledge extracted from a coding session."""

    id: str  # UUID v4
    content: str  # Description of the learning
    category: str  # Category enum value
    spec_name: str  # Source specification name
    keywords: list[str]  # Relevant terms for matching
    confidence: str  # "high" | "medium" | "low"
    created_at: str  # ISO 8601 timestamp
    supersedes: str | None = None  # UUID of the fact this one replaces
    session_id: str | None = None  # Node ID of the session that produced this fact
    commit_sha: str | None = None  # Git commit SHA associated with this fact
