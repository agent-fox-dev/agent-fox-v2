"""Shared CLI path constants.

Centralizes the `.agent-fox` directory name and knowledge database path
so they are defined once and imported by CLI commands that need them.
"""

from __future__ import annotations

from pathlib import Path

AGENT_FOX_DIR = ".agent-fox"
DEFAULT_DB_PATH = Path(".agent-fox/knowledge.duckdb")
