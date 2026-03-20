"""Backward-compatible re-export. Use ``agent_fox.routing.core`` directly."""

from agent_fox.routing.core import (
    count_outcomes,
    persist_assessment,
    persist_outcome,
    query_outcomes,
)

__all__ = [
    "persist_assessment",
    "persist_outcome",
    "count_outcomes",
    "query_outcomes",
]
