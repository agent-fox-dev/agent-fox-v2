"""Shared audit event helper for night-shift modules.

Requirements: 61-REQ-8.4 (observability)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Stable run ID shared across all audit events in one nightshift process.
# Generated lazily on first use so imports remain side-effect-free.
_run_id: str | None = None


def _get_run_id() -> str:
    """Return (or lazily create) the module-level nightshift run ID."""
    global _run_id
    if _run_id is None:
        from agent_fox.knowledge.audit import generate_run_id

        _run_id = generate_run_id()
    return _run_id


def emit_audit_event(
    event_type_name: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Emit a night-shift audit event (best-effort).

    Writes to the JSONL audit sink under ``.agent-fox/audit/``.
    Silently skips if audit infrastructure is unavailable.

    Requirements: 61-REQ-8.4 (observability)
    """
    try:
        from agent_fox.knowledge.audit import (
            AuditEvent,
            AuditEventType,
            AuditJsonlSink,
        )

        event_type = AuditEventType(event_type_name)
        run_id = _get_run_id()
        event = AuditEvent(
            run_id=run_id,
            event_type=event_type,
            payload=payload or {},
        )
        audit_dir = Path.cwd() / ".agent-fox" / "audit"
        sink = AuditJsonlSink(audit_dir, run_id)
        sink.emit_audit_event(event)
        logger.debug("Audit event: %s payload=%s", event.event_type, event.payload)
    except Exception:  # noqa: BLE001
        logger.debug("Failed to emit audit event: %s", event_type_name, exc_info=True)
