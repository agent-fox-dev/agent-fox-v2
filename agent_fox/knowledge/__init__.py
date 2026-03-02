"""DuckDB knowledge store infrastructure for agent-fox.

Provides database lifecycle management, schema creation and versioning,
the SessionSink protocol, the DuckDB sink, the JSONL sink, and graceful
degradation.
"""

from agent_fox.knowledge.db import KnowledgeDB, open_knowledge_store
from agent_fox.knowledge.duckdb_sink import DuckDBSink
from agent_fox.knowledge.jsonl_sink import JsonlSink
from agent_fox.knowledge.sink import (
    SessionOutcome,
    SessionSink,
    SinkDispatcher,
    ToolCall,
    ToolError,
)

__all__ = [
    "DuckDBSink",
    "JsonlSink",
    "KnowledgeDB",
    "SessionOutcome",
    "SessionSink",
    "SinkDispatcher",
    "ToolCall",
    "ToolError",
    "open_knowledge_store",
]
