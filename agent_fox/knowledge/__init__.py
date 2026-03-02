"""DuckDB knowledge store infrastructure for agent-fox.

Provides database lifecycle management, schema creation and versioning,
the SessionSink protocol, the DuckDB sink, the JSONL sink, and graceful
degradation.
"""

from agent_fox.knowledge.db import KnowledgeDB, open_knowledge_store

__all__ = [
    "KnowledgeDB",
    "open_knowledge_store",
]
