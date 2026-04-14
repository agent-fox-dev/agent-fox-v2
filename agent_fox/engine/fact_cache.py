"""Fact cache — superseded by AdaptiveRetriever (spec 104).

Legacy classes and functions removed per 104-REQ-6.4. All retrieval now
goes through agent_fox.knowledge.retrieval.AdaptiveRetriever.

Internal helpers retained for use by other modules.
"""

from __future__ import annotations


def _extract_keywords(content: str) -> list[str]:
    """Extract simple keywords from fact content for scoring."""
    # Simple word extraction - split on whitespace and punctuation
    words = content.lower().split()
    # Filter short words and common stop words
    stop_words = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "and",
        "or",
        "not",
        "this",
        "that",
        "it",
    }
    return [
        w.strip(".,;:!?()[]{}\"'") for w in words if len(w) > 2 and w.lower().strip(".,;:!?()[]{}\"'") not in stop_words
    ]


def _ensure_iso(ts: object) -> str:
    """Convert a timestamp to ISO 8601 string with UTC timezone."""
    from agent_fox.core.models import ensure_iso

    return ensure_iso(ts)


def _now_iso() -> str:
    """Return current UTC timestamp as ISO 8601 string."""
    from datetime import UTC, datetime

    return datetime.now(tz=UTC).isoformat()
