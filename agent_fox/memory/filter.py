"""Context selection: choose relevant facts for a coding session.

Requirements: 05-REQ-4.1, 05-REQ-4.2, 05-REQ-4.3, 05-REQ-4.E1,
              05-REQ-4.E2
"""

from __future__ import annotations

import logging
from datetime import datetime

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
        A list of up to `budget` facts, sorted by relevance score
        (highest first).
    """
    raise NotImplementedError


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
    raise NotImplementedError
