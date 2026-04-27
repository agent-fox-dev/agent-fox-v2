"""Shared audit-event emission and cost helpers.

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
    from agent_fox.core.config import AgentFoxConfig
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


def calculate_session_cost(
    config: AgentFoxConfig,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> float:
    """Calculate session cost from token counts and pricing config."""
    from agent_fox.core.config import PricingConfig
    from agent_fox.core.models import calculate_cost

    pricing = getattr(config, "pricing", PricingConfig())
    return calculate_cost(
        input_tokens,
        output_tokens,
        model_id,
        pricing,
        cache_read_input_tokens=cache_read_input_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
    )
