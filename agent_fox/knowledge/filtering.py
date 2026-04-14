"""Context selection — superseded by AdaptiveRetriever (spec 104).

Legacy functions removed per 104-REQ-6.1. All retrieval now goes through
agent_fox.knowledge.retrieval.AdaptiveRetriever.

Constants are retained for backward compatibility with config references.
"""

from __future__ import annotations

MAX_CONTEXT_FACTS = 50
DEFAULT_CONFIDENCE_THRESHOLD = 0.5
