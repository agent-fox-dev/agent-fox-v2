"""Knowledge management for agent-fox.

Provides the KnowledgeProvider protocol, DuckDB knowledge store
infrastructure, schema management, audit/sink infrastructure, review
store, and agent trace.
"""

from agent_fox.knowledge.fox_provider import KnowledgeProvider, NoOpKnowledgeProvider

__all__ = [
    "KnowledgeProvider",
    "NoOpKnowledgeProvider",
]
