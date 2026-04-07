"""Shared audit-event emission helper.

Eliminates the _emit_audit() method duplicated across Orchestrator,
SessionResultHandler, and NodeSessionRunner.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent_fox.knowledge.audit import (
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    default_severity_for,
)

if TYPE_CHECKING:
    from agent_fox.knowledge.sink import SessionSink, SinkDispatcher

logger = logging.getLogger(__name__)


def emit_audit_event(
    sink: SinkDispatcher | SessionSink | None,
    run_id: str,
    event_type: AuditEventType,
    *,
    node_id: str = "",
    session_id: str = "",
    archetype: str = "",
    severity: AuditSeverity | None = None,
    payload: dict | None = None,
) -> None:
    """Emit an audit event to the sink dispatcher (best-effort).

    Requirements: 40-REQ-7.1, 40-REQ-7.2, 40-REQ-7.3, 40-REQ-9.1,
                  40-REQ-9.2, 40-REQ-9.3, 40-REQ-9.4, 40-REQ-9.5,
                  40-REQ-10.1, 40-REQ-10.2, 40-REQ-11.3
    """
    if sink is None or not run_id:
        return
    try:
        event = AuditEvent(
            run_id=run_id,
            event_type=event_type,
            severity=severity or default_severity_for(event_type),
            node_id=node_id,
            session_id=session_id,
            archetype=archetype,
            payload=payload or {},
        )
        sink.emit_audit_event(event)
    except Exception:
        logger.debug(
            "Failed to emit audit event %s",
            event_type,
            exc_info=True,
        )
