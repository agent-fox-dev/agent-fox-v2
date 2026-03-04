"""Predictive pattern detection: recurring cause-effect patterns.

Requirements: 13-REQ-5.1, 13-REQ-5.2, 13-REQ-5.3, 13-REQ-5.E1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import duckdb  # noqa: F401

logger = logging.getLogger("agent_fox.knowledge.patterns")


@dataclass(frozen=True)
class Pattern:
    """A recurring cause-effect pattern detected in history."""

    trigger: str  # e.g., "changes to src/auth/"
    effect: str  # e.g., "test_payments.py failures"
    occurrences: int  # number of times this pattern was observed
    last_seen: str  # ISO timestamp of most recent occurrence
    confidence: str  # "high" (5+), "medium" (3-4), "low" (2)


def _assign_confidence(occurrences: int) -> str:
    """Assign confidence level based on occurrence count."""
    if occurrences >= 5:
        return "high"
    if occurrences >= 3:
        return "medium"
    return "low"


def detect_patterns(
    conn: duckdb.DuckDBPyConnection,
    *,
    min_occurrences: int = 2,
) -> list[Pattern]:
    """Detect recurring cause-effect patterns.

    Analysis algorithm:
    1. Query session_outcomes for all sessions, grouping by spec_name
       and touched_path.
    2. For each pair of (path_changed, subsequent_failure), count
       co-occurrences across sessions.
    3. Cross-reference with fact_causes to find causal chains that
       connect the change to the failure.
    4. Rank patterns by occurrence count, then by recency.
    5. Assign confidence: high (5+ occurrences), medium (3-4), low (2).

    Returns patterns sorted by occurrence count descending.
    """
    query = """
    SELECT
        changed.touched_path AS trigger_path,
        failed.touched_path  AS failed_path,
        COUNT(*)             AS occurrences,
        MAX(failed.created_at) AS last_seen
    FROM session_outcomes changed
    JOIN session_outcomes failed
        ON changed.spec_name != failed.spec_name
        AND changed.created_at <= failed.created_at
        AND failed.created_at <= changed.created_at + INTERVAL 1 DAY
        AND failed.status = 'failed'
        AND changed.status = 'completed'
    -- Validate against causal graph: require a causal link between
    -- facts from the triggering and failing sessions.
    JOIN memory_facts mf_cause
        ON mf_cause.session_id = changed.node_id
    JOIN memory_facts mf_effect
        ON mf_effect.session_id = failed.node_id
    JOIN fact_causes fc
        ON fc.cause_id = mf_cause.id
        AND fc.effect_id = mf_effect.id
    WHERE changed.touched_path IS NOT NULL
      AND failed.touched_path IS NOT NULL
    GROUP BY changed.touched_path, failed.touched_path
    HAVING COUNT(*) >= ?
    ORDER BY occurrences DESC, last_seen DESC
    """
    try:
        rows = conn.execute(query, [min_occurrences]).fetchall()
    except Exception:
        logger.warning("Pattern detection query failed", exc_info=True)
        return []

    patterns: list[Pattern] = []
    for row in rows:
        trigger_path = str(row[0])
        failed_path = str(row[1])
        occurrences = int(row[2])
        last_seen = str(row[3]) if row[3] is not None else ""

        patterns.append(
            Pattern(
                trigger=trigger_path,
                effect=f"{failed_path} failures",
                occurrences=occurrences,
                last_seen=last_seen,
                confidence=_assign_confidence(occurrences),
            )
        )

    return patterns


def render_patterns(patterns: list[Pattern], *, use_color: bool = True) -> str:
    """Render detected patterns as formatted text.

    Each pattern is rendered as:
        trigger -> effect (N occurrences, last seen DATE, confidence LEVEL)

    When use_color is False, no ANSI escape codes are included.
    """
    if not patterns:
        return "No recurring patterns detected. More session history is needed."

    lines: list[str] = []
    for p in patterns:
        line = (
            f"{p.trigger} -> {p.effect} "
            f"({p.occurrences} occurrences, "
            f"last seen {p.last_seen}, "
            f"confidence {p.confidence})"
        )
        lines.append(line)

    return "\n".join(lines)
