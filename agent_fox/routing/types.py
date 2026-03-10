"""Data types for adaptive model routing.

Defines the core data structures used across the routing system:
FeatureVector, ComplexityAssessment, and ExecutionOutcome.

Requirements: 30-REQ-1.1, 30-REQ-1.2, 30-REQ-3.1
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agent_fox.core.config import RoutingConfig
from agent_fox.core.models import ModelTier

# Re-export RoutingConfig so tests can import from routing.types
__all__ = [
    "FeatureVector",
    "ComplexityAssessment",
    "ExecutionOutcome",
    "RoutingConfig",
]


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
