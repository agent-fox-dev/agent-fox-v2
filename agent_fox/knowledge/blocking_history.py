"""Blocking decision tracking and threshold learning.

Records blocking decisions (skeptic/oracle blocking a spec from proceeding)
and their outcomes, then computes optimal thresholds that minimize false
positives while maintaining an acceptable false negative rate.

Requirements: 39-REQ-10.1, 39-REQ-10.2, 39-REQ-10.3
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import duckdb

logger = logging.getLogger(__name__)


@dataclass
class BlockingDecision:
    """A recorded blocking decision with its outcome.

    Attributes:
        spec_name: The specification being reviewed.
        archetype: The archetype making the decision ("skeptic" or "oracle").
        critical_count: Number of critical findings detected.
        threshold: The threshold that was applied.
        blocked: Whether the spec was actually blocked.
        outcome: The assessed correctness of the decision:
            "correct_block" - blocked and should have been blocked
            "false_positive" - blocked but should not have been
            "correct_pass" - passed and should have passed
            "missed_block" - passed but should have been blocked
    """

    spec_name: str
    archetype: str
    critical_count: int
    threshold: int
    blocked: bool
    outcome: str


def record_blocking_decision(
    conn: duckdb.DuckDBPyConnection,
    decision: BlockingDecision,
) -> None:
    """Record a blocking decision for threshold learning.

    Args:
        conn: DuckDB connection with blocking_history table.
        decision: The blocking decision to record.

    Requirements: 39-REQ-10.1
    """
    decision_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO blocking_history
           (id, spec_name, archetype, critical_count, threshold,
            blocked, outcome, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, current_timestamp)""",
        [
            decision_id,
            decision.spec_name,
            decision.archetype,
            decision.critical_count,
            decision.threshold,
            decision.blocked,
            decision.outcome,
        ],
    )


def compute_optimal_threshold(
    conn: duckdb.DuckDBPyConnection,
    archetype: str,
    min_decisions: int = 20,
    max_false_negative_rate: float = 0.1,
) -> int | None:
    """Compute optimal threshold from blocking history.

    Finds the threshold that minimizes false positives while keeping
    the false negative rate at or below max_false_negative_rate.

    A false negative occurs when the threshold is too high: findings
    that should have blocked didn't. A false positive occurs when the
    threshold is too low: findings that shouldn't have blocked did.

    The algorithm:
    1. Collect all decisions with outcomes for the given archetype.
    2. If fewer than min_decisions exist, return None.
    3. For each candidate threshold (1..max_critical_count), compute
       FPR and FNR, and select the threshold that minimizes FP while
       keeping FNR <= max_false_negative_rate.

    Args:
        conn: DuckDB connection with blocking_history table.
        archetype: The archetype type ("skeptic" or "oracle").
        min_decisions: Minimum number of decisions before learning.
        max_false_negative_rate: Maximum acceptable FNR.

    Returns:
        Optimal threshold as an integer, or None if insufficient data.

    Requirements: 39-REQ-10.2
    """
    try:
        rows = conn.execute(
            """SELECT critical_count, outcome
               FROM blocking_history
               WHERE archetype = ? AND outcome IS NOT NULL""",
            [archetype],
        ).fetchall()
    except duckdb.Error:
        logger.warning("Failed to query blocking history", exc_info=True)
        return None

    if len(rows) < min_decisions:
        return None

    # Categorize decisions by their ground truth
    # "correct_block" and "missed_block" mean "should have blocked"
    # "correct_pass" and "false_positive" mean "should have passed"
    decisions: list[tuple[int, bool]] = []  # (critical_count, should_block)
    for critical_count, outcome in rows:
        should_block = outcome in ("correct_block", "missed_block")
        decisions.append((critical_count, should_block))

    # Find the range of critical counts
    max_count = max(cc for cc, _ in decisions)

    best_threshold = 1
    best_fp_count = len(decisions)  # worst case

    for candidate in range(1, max_count + 2):
        # With this threshold: block if critical_count > candidate
        fn_count = 0  # should_block but critical_count <= candidate
        fp_count = 0  # should_not_block but critical_count > candidate
        total_should_block = 0
        total_should_not_block = 0

        for cc, should_block in decisions:
            if should_block:
                total_should_block += 1
                if cc <= candidate:
                    fn_count += 1
            else:
                total_should_not_block += 1
                if cc > candidate:
                    fp_count += 1

        # Compute FNR
        if total_should_block > 0:
            fnr = fn_count / total_should_block
        else:
            fnr = 0.0

        # Only consider thresholds that satisfy FNR constraint
        if fnr <= max_false_negative_rate:
            if fp_count < best_fp_count:
                best_fp_count = fp_count
                best_threshold = candidate

    return best_threshold
