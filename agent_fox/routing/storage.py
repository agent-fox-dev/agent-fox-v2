"""DuckDB CRUD operations for complexity assessments and execution outcomes.

All operations are best-effort: errors are caught and logged rather than
propagated, so that DB failures never block task execution.

Requirements: 30-REQ-1.6, 30-REQ-3.1, 30-REQ-3.2, 30-REQ-3.E1
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict

import duckdb

from agent_fox.routing.types import ComplexityAssessment, ExecutionOutcome

logger = logging.getLogger(__name__)


def _feature_vector_to_json(fv: object) -> str:
    """Serialize a FeatureVector dataclass to a JSON string."""
    return json.dumps(asdict(fv))  # type: ignore[arg-type]


def persist_assessment(
    conn: duckdb.DuckDBPyConnection,
    assessment: ComplexityAssessment,
) -> None:
    """Persist a complexity assessment to the complexity_assessments table.

    Best-effort: logs a warning on failure, never raises.

    Requirements: 30-REQ-1.6
    """
    try:
        conn.execute(
            """INSERT INTO complexity_assessments
               (id, node_id, spec_name, task_group, predicted_tier,
                confidence, assessment_method, feature_vector, tier_ceiling, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                assessment.id,
                assessment.node_id,
                assessment.spec_name,
                assessment.task_group,
                str(assessment.predicted_tier),
                assessment.confidence,
                assessment.assessment_method,
                _feature_vector_to_json(assessment.feature_vector),
                str(assessment.tier_ceiling),
                assessment.created_at,
            ],
        )
    except Exception:
        logger.warning(
            "Failed to persist assessment %s for node %s",
            assessment.id,
            assessment.node_id,
            exc_info=True,
        )


def persist_outcome(
    conn: duckdb.DuckDBPyConnection,
    outcome: ExecutionOutcome,
) -> None:
    """Persist an execution outcome to the execution_outcomes table.

    Best-effort: logs a warning on failure, never raises.

    Requirements: 30-REQ-3.1, 30-REQ-3.E1
    """
    try:
        conn.execute(
            """INSERT INTO execution_outcomes
               (id, assessment_id, actual_tier, total_tokens, total_cost,
                duration_ms, attempt_count, escalation_count, outcome,
                files_touched_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                outcome.id,
                outcome.assessment_id,
                str(outcome.actual_tier),
                outcome.total_tokens,
                outcome.total_cost,
                outcome.duration_ms,
                outcome.attempt_count,
                outcome.escalation_count,
                outcome.outcome,
                outcome.files_touched_count,
                outcome.created_at,
            ],
        )
    except Exception:
        logger.warning(
            "Failed to persist outcome %s for assessment %s",
            outcome.id,
            outcome.assessment_id,
            exc_info=True,
        )


def count_outcomes(conn: duckdb.DuckDBPyConnection) -> int:
    """Return the number of execution outcome records.

    Returns 0 on any error.
    """
    try:
        result = conn.execute("SELECT COUNT(*) FROM execution_outcomes").fetchone()
        return int(result[0]) if result else 0
    except Exception:
        logger.warning("Failed to count execution outcomes", exc_info=True)
        return 0


def query_outcomes(
    conn: duckdb.DuckDBPyConnection,
) -> list[tuple]:
    """Query all assessment+outcome pairs for training.

    Returns a list of (feature_vector_json, actual_tier) tuples.
    Returns an empty list on any error.
    """
    try:
        return conn.execute(
            """SELECT a.feature_vector, o.actual_tier
               FROM execution_outcomes o
               JOIN complexity_assessments a ON o.assessment_id = a.id"""
        ).fetchall()
    except Exception:
        logger.warning("Failed to query outcomes for training", exc_info=True)
        return []
