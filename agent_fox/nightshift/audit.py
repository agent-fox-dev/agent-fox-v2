"""Shared audit event helper for night-shift modules.

Requirements: 61-REQ-8.4 (observability)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def emit_audit_event(
    event_type_name: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Emit a night-shift audit event (best-effort).

    Silently skips if audit infrastructure is unavailable.

    Requirements: 61-REQ-8.4 (observability)
    """
    try:
        from agent_fox.knowledge.audit import (
            AuditEvent,
            AuditEventType,
            generate_run_id,
        )

        event_type = AuditEventType(event_type_name)
        event = AuditEvent(
            run_id=generate_run_id(),
            event_type=event_type,
            payload=payload or {},
        )
        logger.debug("Audit event: %s payload=%s", event.event_type, event.payload)
    except Exception:  # noqa: BLE001
        logger.debug("Failed to emit audit event: %s", event_type_name, exc_info=True)
