"""Backward-compatible re-export. Use ``agent_fox.routing.core`` directly."""

from agent_fox.core.config import RoutingConfig
from agent_fox.routing.core import ComplexityAssessment, ExecutionOutcome, FeatureVector

__all__ = [
    "FeatureVector",
    "ComplexityAssessment",
    "ExecutionOutcome",
    "RoutingConfig",
]
