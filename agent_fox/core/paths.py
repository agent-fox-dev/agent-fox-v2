"""Shared path constants for the .agent-fox project directory.

Centralizes all ``.agent-fox/`` paths so they are defined once and
imported by any layer without introducing circular dependencies.
"""

from __future__ import annotations

from pathlib import Path

AGENT_FOX_DIR = ".agent-fox"
DEFAULT_DB_PATH = Path(".agent-fox/knowledge.duckdb")
PLAN_PATH = Path(".agent-fox/plan.json")
STATE_PATH = Path(".agent-fox/state.jsonl")
MEMORY_PATH = Path(".agent-fox/memory.jsonl")
AUDIT_DIR = Path(".agent-fox/audit")
