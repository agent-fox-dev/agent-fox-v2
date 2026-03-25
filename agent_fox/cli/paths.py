"""Backward-compatible re-export. Use ``agent_fox.core.paths`` directly."""

from agent_fox.core.paths import (
    AGENT_FOX_DIR,
    AUDIT_DIR,
    DEFAULT_DB_PATH,
    MEMORY_PATH,
    PLAN_PATH,
    STATE_PATH,
)

__all__ = [
    "AGENT_FOX_DIR",
    "AUDIT_DIR",
    "DEFAULT_DB_PATH",
    "MEMORY_PATH",
    "PLAN_PATH",
    "STATE_PATH",
]
