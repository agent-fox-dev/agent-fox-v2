"""Consolidated knowledge management for agent-fox.

Provides fact storage, DuckDB knowledge store infrastructure, schema
management, embedding and search, fact extraction, filtering, rendering,
compaction, and the in-memory state machine for buffered writes.
"""

from agent_fox.knowledge.audit import (
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    generate_run_id,
)
from agent_fox.knowledge.compaction import compact
from agent_fox.knowledge.extraction import extract_facts
from agent_fox.knowledge.facts import (
    CONFIDENCE_MAP,
    DEFAULT_CONFIDENCE,
    Category,
    ConfidenceLevel,
    Fact,
    parse_confidence,
)
from agent_fox.knowledge.filtering import select_relevant_facts
from agent_fox.knowledge.rendering import render_summary
from agent_fox.knowledge.state_machine import KnowledgeStateMachine
from agent_fox.knowledge.store import (
    DEFAULT_MEMORY_PATH,
    MemoryStore,
    append_facts,
    export_facts_to_jsonl,
    load_all_facts,
    load_facts_by_spec,
    load_facts_from_jsonl,
    read_all_facts,
    write_facts,
)

__all__ = [
    "AuditEvent",
    "AuditEventType",
    "AuditSeverity",
    "CONFIDENCE_MAP",
    "DEFAULT_CONFIDENCE",
    "DEFAULT_MEMORY_PATH",
    "Category",
    "ConfidenceLevel",
    "Fact",
    "KnowledgeStateMachine",
    "MemoryStore",
    "append_facts",
    "compact",
    "export_facts_to_jsonl",
    "extract_facts",
    "generate_run_id",
    "load_all_facts",
    "load_facts_by_spec",
    "load_facts_from_jsonl",
    "read_all_facts",
    "parse_confidence",
    "render_summary",
    "select_relevant_facts",
    "write_facts",
]
