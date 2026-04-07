"""Core data types and persistence for adaptive model routing.

Combines the routing data model (FeatureVector, ComplexityAssessment,
ExecutionOutcome) with DuckDB CRUD operations, since the persistence
layer is tightly coupled to the data types.

Requirements: 30-REQ-1.1, 30-REQ-1.2, 30-REQ-1.6, 30-REQ-3.1, 30-REQ-3.2, 30-REQ-3.E1
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime

import duckdb

from agent_fox.core.config import RoutingConfig
from agent_fox.core.models import ModelTier

logger = logging.getLogger(__name__)

# Re-export RoutingConfig so consumers can import from routing.core
__all__ = [
    "FeatureVector",
    "ComplexityAssessment",
    "ExecutionOutcome",
    "RoutingConfig",
    "persist_assessment",
    "persist_outcome",
    "count_outcomes",
    "query_outcomes",
]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureVector:
    """Numeric and categorical attributes extracted from a task group's spec content.

    Used as input to the heuristic and statistical assessors.
    """

    subtask_count: int
    spec_word_count: int
    has_property_tests: bool
    edge_case_count: int
    dependency_count: int
    archetype: str
    # New fields (54-REQ-3.1, 54-REQ-4.1, 54-REQ-5.1, 54-REQ-6.1)
    file_count_estimate: int = 0
    cross_spec_integration: bool = False
    language_count: int = 1
    historical_median_duration_ms: int | None = None


@dataclass(frozen=True)
class ComplexityAssessment:
    """Pre-execution prediction of which model tier a task group requires.

    Produced by the assessment pipeline and persisted to DuckDB before
    execution begins.
    """

    id: str  # UUID
    node_id: str
    spec_name: str
    task_group: int
    predicted_tier: ModelTier
    confidence: float  # [0.0, 1.0]
    assessment_method: str  # "heuristic" | "statistical" | "llm" | "hybrid"
    feature_vector: FeatureVector
    tier_ceiling: ModelTier
    created_at: datetime


@dataclass(frozen=True)
class ExecutionOutcome:
    """Post-execution record of actual resource consumption and outcome.

    Linked to a ComplexityAssessment via assessment_id. Used for
    calibration and statistical model training.
    """

    id: str  # UUID
    assessment_id: str  # FK to ComplexityAssessment
    actual_tier: ModelTier
    total_tokens: int
    total_cost: float
    duration_ms: int
    attempt_count: int
    escalation_count: int
    outcome: str  # "completed" | "failed"
    files_touched_count: int
    created_at: datetime


# ---------------------------------------------------------------------------
# DuckDB persistence (best-effort: errors are logged, never propagated)
# ---------------------------------------------------------------------------


def _feature_vector_to_json(fv: FeatureVector) -> str:
    """Serialize a FeatureVector dataclass to a JSON string."""
    return json.dumps(asdict(fv))


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
