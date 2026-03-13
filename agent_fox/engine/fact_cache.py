"""Pre-computed ranked fact cache for session context assembly.

Computes and caches per-spec fact relevance rankings at plan time to
avoid per-session re-computation. The cache is invalidated when new
facts are added or existing facts are superseded.

Requirements: 39-REQ-5.1, 39-REQ-5.2, 39-REQ-5.3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import duckdb

from agent_fox.knowledge.facts import Fact, parse_confidence
from agent_fox.knowledge.filtering import select_relevant_facts

logger = logging.getLogger(__name__)


@dataclass
class RankedFactCache:
    """Cached ranked facts for a single spec.

    Attributes:
        spec_name: The specification this cache applies to.
        ranked_facts: Pre-ranked list of relevant facts.
        created_at: ISO 8601 timestamp of cache creation.
        fact_count_at_creation: Total fact count when cache was built,
            used for staleness detection.
    """

    spec_name: str
    ranked_facts: list[Fact]
    created_at: str
    fact_count_at_creation: int


def precompute_fact_rankings(
    conn: duckdb.DuckDBPyConnection,
    spec_names: list[str],
    confidence_threshold: float = 0.5,
) -> dict[str, RankedFactCache]:
    """Pre-compute and cache ranked fact lists for all specs.

    Queries all non-superseded facts from DuckDB, runs relevance scoring
    per spec, and returns a dict of cached rankings.

    Requirements: 39-REQ-5.1
    """
    # Load all active facts from DB
    rows = conn.execute(
        "SELECT CAST(id AS VARCHAR), content, category, spec_name, "
        "confidence, created_at, CAST(superseded_by AS VARCHAR), "
        "session_id, commit_sha "
        "FROM memory_facts WHERE superseded_by IS NULL"
    ).fetchall()

    all_facts: list[Fact] = []
    for row in rows:
        (
            fact_id,
            content,
            category,
            spec_name,
            confidence,
            created_at,
            _,
            session_id,
            commit_sha,
        ) = row

        conf_val = parse_confidence(confidence)
        all_facts.append(
            Fact(
                id=str(fact_id),
                content=content or "",
                category=category or "pattern",
                spec_name=spec_name or "",
                keywords=_extract_keywords(content or ""),
                confidence=conf_val,
                created_at=_ensure_iso(created_at),
                session_id=session_id,
                commit_sha=commit_sha,
            )
        )

    total_fact_count = len(all_facts)
    now = _now_iso()

    cache: dict[str, RankedFactCache] = {}
    for spec in spec_names:
        # Use spec name as keyword for relevance scoring
        ranked = select_relevant_facts(
            all_facts,
            spec,
            [spec],
            confidence_threshold=confidence_threshold,
        )
        cache[spec] = RankedFactCache(
            spec_name=spec,
            ranked_facts=ranked,
            created_at=now,
            fact_count_at_creation=total_fact_count,
        )

    return cache


def get_cached_facts(
    cache: dict[str, RankedFactCache],
    spec_name: str,
    current_fact_count: int,
) -> list[Fact] | None:
    """Return cached facts if still valid, None if stale or missing.

    The cache is considered stale when the current fact count differs
    from the count at creation time — indicating facts have been added
    or superseded since the cache was built.

    Requirements: 39-REQ-5.2, 39-REQ-5.3
    """
    entry = cache.get(spec_name)
    if entry is None:
        return None

    if entry.fact_count_at_creation != current_fact_count:
        return None

    return entry.ranked_facts


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
        w.strip(".,;:!?()[]{}\"'")
        for w in words
        if len(w) > 2 and w.lower().strip(".,;:!?()[]{}\"'") not in stop_words
    ]


def _ensure_iso(ts: object) -> str:
    """Convert a timestamp to ISO 8601 string with UTC timezone.

    Handles naive datetime objects by assuming UTC.
    """
    from datetime import UTC, datetime

    if ts is None:
        return datetime.now(tz=UTC).isoformat()
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts.isoformat()
    return str(ts)


def _now_iso() -> str:
    """Return current UTC timestamp as ISO 8601 string."""
    from datetime import UTC, datetime

    return datetime.now(tz=UTC).isoformat()
