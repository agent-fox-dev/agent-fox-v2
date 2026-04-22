"""Knowledge management for agent-fox.

Provides the KnowledgeProvider protocol, DuckDB knowledge store
infrastructure, schema management, audit/sink infrastructure, review
store, blocking history, and agent trace.
"""

from agent_fox.knowledge.provider import KnowledgeProvider, NoOpKnowledgeProvider

__all__ = [
    "KnowledgeProvider",
    "NoOpKnowledgeProvider",
]
