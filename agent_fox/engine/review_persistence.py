"""Post-session review finding persistence.

Extracted from session_lifecycle.py to reduce the NodeSessionRunner
god class. Handles parsing and persisting structured findings from
review archetypes (skeptic, verifier, oracle, auditor).

Requirements: 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent_fox.core.json_extraction import extract_json_array
from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.knowledge.audit import AuditEventType, AuditSeverity
from agent_fox.knowledge.sink import SessionOutcome, SinkDispatcher

logger = logging.getLogger(__name__)


def record_session_to_sink(
    sink: SinkDispatcher | None,
    outcome: SessionOutcome,
    node_id: str,
) -> None:
    """Record a session outcome to the sink dispatcher (best-effort)."""
    if sink is None:
        return
    try:
        sink.record_session_outcome(outcome)
    except Exception:
        logger.warning(
            "Failed to record session outcome to sink for %s",
            node_id,
            exc_info=True,
        )


def persist_review_findings(
    transcript: str,
    node_id: str,
    attempt: int,
    *,
    archetype: str,
    spec_name: str,
    task_group: int | str,
    knowledge_db_conn: Any,
    sink: SinkDispatcher | None,
    run_id: str,
) -> None:
    """Parse and persist structured findings from review archetypes.

    Uses extract_json_array to extract JSON from archetype output, then
    routes to the correct typed parser and insert function based on
    archetype:
    - skeptic  -> parse_review_findings   -> insert_findings
    - verifier -> parse_verification_results -> insert_verdicts
    - oracle   -> parse_drift_findings    -> insert_drift_findings

    Non-review archetypes (coder, librarian, etc.) are silently skipped.

    Requirements: 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1,
                  53-REQ-1.E1, 53-REQ-2.E1, 53-REQ-3.E1
    """
    if archetype not in ("skeptic", "verifier", "oracle", "auditor"):
        return

    session_id = f"{node_id}:{attempt}"
    tg = str(task_group)

    try:
        if archetype in ("skeptic", "verifier", "oracle"):
            json_objects = extract_json_array(transcript)
            if json_objects is None:
                emit_audit_event(
                    sink,
                    run_id,
                    AuditEventType.REVIEW_PARSE_FAILURE,
                    node_id=node_id,
                    archetype=archetype,
                    severity=AuditSeverity.WARNING,
                    payload={"raw_output": transcript[:2000]},
                )
                return

            from agent_fox.engine.review_parser import (
                parse_drift_findings,
                parse_review_findings,
                parse_verification_results,
            )
            from agent_fox.knowledge.review_store import (
                insert_drift_findings,
                insert_findings,
                insert_verdicts,
            )

            # Dispatch table: archetype -> (parser, inserter, label)
            _review_dispatch = {
                "skeptic": (
                    parse_review_findings,
                    insert_findings,
                    "skeptic findings",
                ),
                "verifier": (
                    parse_verification_results,
                    insert_verdicts,
                    "verifier verdicts",
                ),
                "oracle": (
                    parse_drift_findings,
                    insert_drift_findings,
                    "oracle drift findings",
                ),
            }
            parser, inserter, label = _review_dispatch[archetype]
            records = parser(json_objects, spec_name, tg, session_id)
            if records:
                count = inserter(knowledge_db_conn, records)
                logger.info("Persisted %d %s for %s", count, label, node_id)
            else:
                emit_audit_event(
                    sink,
                    run_id,
                    AuditEventType.REVIEW_PARSE_FAILURE,
                    node_id=node_id,
                    archetype=archetype,
                    severity=AuditSeverity.WARNING,
                    payload={"raw_output": transcript[:2000]},
                )

        elif archetype == "auditor":
            from agent_fox.session.auditor_output import persist_auditor_results
            from agent_fox.session.review_parser import parse_auditor_output

            audit_result = parse_auditor_output(transcript)
            if audit_result is not None:
                spec_dir = Path.cwd() / ".specs" / spec_name
                persist_auditor_results(spec_dir, audit_result, attempt=attempt)

    except Exception:
        logger.warning(
            "Failed to persist %s findings for %s, continuing",
            archetype,
            node_id,
            exc_info=True,
        )
