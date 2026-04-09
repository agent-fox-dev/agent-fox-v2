"""Core data types for adaptive model routing.

Defines the data model used by the escalation ladder subsystem.
Prediction pipeline dataclasses (FeatureVector, ComplexityAssessment,
ExecutionOutcome) are retained for backward compatibility.

Requirements: 89-REQ-2.4
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from agent_fox.core.config import RoutingConfig
from agent_fox.core.models import ModelTier

logger = logging.getLogger(__name__)

# Re-export RoutingConfig so consumers can import from routing.core
__all__ = [
    "FeatureVector",
    "ComplexityAssessment",
    "ExecutionOutcome",
    "RoutingConfig",
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

    Retained for backward compatibility. No longer populated by the routing
    subsystem after removal of the prediction pipeline.
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

    Retained for backward compatibility. No longer persisted to DuckDB after
    removal of the prediction pipeline.
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
