"""Context selection: choose relevant facts for a coding session.

Requirements: 05-REQ-4.1, 05-REQ-4.2, 05-REQ-4.3, 05-REQ-4.E1,
              05-REQ-4.E2
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from agent_fox.memory.types import Fact

logger = logging.getLogger("agent_fox.memory.filter")

MAX_CONTEXT_FACTS = 50


def select_relevant_facts(
    all_facts: list[Fact],
    spec_name: str,
    task_keywords: list[str],
    budget: int = MAX_CONTEXT_FACTS,
) -> list[Fact]:
    """Select facts relevant to a task, ranked by relevance score.

    Matching criteria:
    - spec_name exact match (facts from the same spec)
    - Keyword overlap between fact keywords and task keywords

    Scoring:
    - keyword_match_count: number of overlapping keywords (case-insensitive)
    - recency_bonus: normalized value between 0 and 1 based on fact age
    - relevance_score = keyword_match_count + recency_bonus

    Args:
        all_facts: Complete list of facts from the knowledge base.
        spec_name: The current task's specification name.
        task_keywords: Keywords describing the current task.
        budget: Maximum number of facts to return (default: 50).

    Returns:
        A list of up to ``budget`` facts, sorted by relevance score
        (highest first).
    """
    if not all_facts:
        return []

    task_keywords_lower: set[str] = {kw.lower() for kw in task_keywords}

    # Filter: a fact is relevant if it shares the spec name OR has keyword overlap.
    relevant: list[Fact] = []
    for fact in all_facts:
        if fact.spec_name == spec_name:
            relevant.append(fact)
            continue
        fact_keywords_lower = {kw.lower() for kw in fact.keywords}
        if fact_keywords_lower & task_keywords_lower:
            relevant.append(fact)

    if not relevant:
        return []

    # Determine the time range across relevant facts for recency scoring.
    now = datetime.now(tz=UTC)
    timestamps = []
    for fact in relevant:
        try:
            timestamps.append(datetime.fromisoformat(fact.created_at))
        except (ValueError, TypeError):
            timestamps.append(now)

    oldest = min(timestamps)

    # Score and sort.
    scored: list[tuple[float, int, Fact]] = []
    for idx, fact in enumerate(relevant):
        score = _compute_relevance_score(
            fact, spec_name, task_keywords_lower, now, oldest
        )
        # Use negative index as tie-breaker to maintain stable ordering.
        scored.append((score, -idx, fact))

    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)

    return [fact for _, _, fact in scored[:budget]]


def _compute_relevance_score(
    fact: Fact,
    spec_name: str,
    task_keywords_lower: set[str],
    now: datetime,
    oldest: datetime,
) -> float:
    """Compute the relevance score for a single fact.

    Score = keyword_match_count + recency_bonus

    The recency bonus is computed as:
        (fact_age_from_oldest) / (total_age_range) if range > 0, else 1.0

    This gives the newest fact a bonus of 1.0 and the oldest a bonus of 0.0.
    """
    # Keyword match count (case-insensitive).
    fact_keywords_lower = {kw.lower() for kw in fact.keywords}
    keyword_match_count = len(fact_keywords_lower & task_keywords_lower)

    # Recency bonus: normalised between 0.0 (oldest) and 1.0 (newest).
    total_range = (now - oldest).total_seconds()
    if total_range > 0:
        try:
            fact_time = datetime.fromisoformat(fact.created_at)
        except (ValueError, TypeError):
            fact_time = now
        age_from_oldest = (fact_time - oldest).total_seconds()
        recency_bonus = age_from_oldest / total_range
    else:
        recency_bonus = 1.0

    return float(keyword_match_count) + recency_bonus
