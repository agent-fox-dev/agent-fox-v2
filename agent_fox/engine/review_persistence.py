"""Post-session review finding persistence.

Extracted from session_lifecycle.py to reduce the NodeSessionRunner
god class. Handles parsing and persisting structured findings from
review archetypes (skeptic, verifier, oracle, auditor).

Requirements: 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1,
              74-REQ-3.*, 74-REQ-4.*, 74-REQ-5.*
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_fox.core.json_extraction import extract_json_array
from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.knowledge.audit import AuditEventType, AuditSeverity
from agent_fox.knowledge.sink import SessionOutcome, SessionSink, SinkDispatcher

if TYPE_CHECKING:
    from agent_fox.knowledge.review_store import ReviewFinding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Format retry constant
# ---------------------------------------------------------------------------

FORMAT_RETRY_PROMPT: str = (
    "Your previous response could not be parsed as valid JSON. "
    "Please output ONLY the structured JSON block with no surrounding text, "
    "no markdown fences, and no commentary. Use exactly the field names "
    "from the schema provided in your instructions."
)

# Extraction strategy names used in parse failure payloads
_STRATEGY_INITIAL = "bracket_scan"
_STRATEGY_RETRY = "retry"


def record_session_to_sink(
    sink: SinkDispatcher | SessionSink | None,
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
    sink: SinkDispatcher | SessionSink | None,
    run_id: str,
    session_handle: Any = None,
) -> None:
    """Parse and persist structured findings from review archetypes.

    Uses extract_json_array to extract JSON from archetype output, then
    routes to the correct typed parser and insert function based on
    archetype:
    - skeptic  -> parse_review_findings   -> insert_findings
    - verifier -> parse_verification_results -> insert_verdicts
    - oracle   -> parse_drift_findings    -> insert_drift_findings

    Non-review archetypes (coder, librarian, etc.) are silently skipped.

    When initial extraction fails and session_handle is alive, a single
    format retry is attempted by appending a user message requesting
    corrected JSON output (74-REQ-3.*).

    Requirements: 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1,
                  53-REQ-1.E1, 53-REQ-2.E1, 53-REQ-3.E1,
                  74-REQ-3.1, 74-REQ-3.2, 74-REQ-3.3, 74-REQ-3.4,
                  74-REQ-3.5, 74-REQ-3.E1, 74-REQ-3.E2,
                  74-REQ-5.1, 74-REQ-5.2, 74-REQ-5.3
    """
    if archetype not in ("skeptic", "verifier", "oracle", "auditor"):
        return

    session_id = f"{node_id}:{attempt}"
    tg = str(task_group)

    try:
        if archetype in ("skeptic", "verifier", "oracle"):
            json_objects = extract_json_array(transcript)

            retry_attempted = False

            if json_objects is None:
                # Attempt format retry if session is still alive (74-REQ-3.1)
                session_is_alive = session_handle is not None and getattr(session_handle, "is_alive", False)

                if session_is_alive:
                    # 74-REQ-3.5: Append to existing session
                    logger.warning(
                        "Initial parse failed for %s %s — attempting format retry",
                        archetype,
                        node_id,
                    )
                    retry_response = session_handle.append_user_message(FORMAT_RETRY_PROMPT)
                    retry_attempted = True
                    # Re-extract from the retry response (74-REQ-3.3: at most 1 retry)
                    json_objects = extract_json_array(retry_response)

                if json_objects is None:
                    # All strategies exhausted — emit parse failure
                    strategy_parts = [_STRATEGY_INITIAL]
                    if retry_attempted:
                        strategy_parts.append(_STRATEGY_RETRY)
                    emit_audit_event(
                        sink,
                        run_id,
                        AuditEventType.REVIEW_PARSE_FAILURE,
                        node_id=node_id,
                        archetype=archetype,
                        severity=AuditSeverity.WARNING,
                        payload={
                            "raw_output": transcript[:2000],
                            "retry_attempted": retry_attempted,
                            "strategy": ",".join(strategy_parts),
                        },
                    )
                    return

                # Retry succeeded
                if retry_attempted:
                    emit_audit_event(
                        sink,
                        run_id,
                        AuditEventType.REVIEW_PARSE_RETRY_SUCCESS,
                        node_id=node_id,
                        archetype=archetype,
                        severity=AuditSeverity.INFO,
                        payload={"archetype": archetype},
                    )

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
                    payload={
                        "raw_output": transcript[:2000],
                        "retry_attempted": retry_attempted,
                        "strategy": _STRATEGY_INITIAL,
                    },
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


# ---------------------------------------------------------------------------
# Partial convergence helpers (74-REQ-4.*)
# ---------------------------------------------------------------------------


def warn_failed_parse_instances(
    raw_results: list[Any],
    archetype: str,
    run_id: str,
) -> None:
    """Log a warning for each instance that failed to produce parseable output.

    Requirements: 74-REQ-4.5
    """
    for i, result in enumerate(raw_results):
        if result is None:
            logger.warning(
                "Instance %d of archetype '%s' failed to parse (run_id=%s)",
                i,
                archetype,
                run_id,
            )


def converge_multi_instance_skeptic(
    raw_results: list[list[ReviewFinding] | None],
    *,
    sink: Any,
    run_id: str,
    node_id: str,
    block_threshold: int,
) -> list[ReviewFinding] | tuple[list[ReviewFinding], bool]:
    """Converge multi-instance skeptic results, filtering failed instances.

    Filters out None results (parse failures), logs warnings for each,
    and passes remaining results to converge_skeptic_records. Emits
    REVIEW_PARSE_FAILURE if all instances failed.

    Requirements: 74-REQ-4.1, 74-REQ-4.4, 74-REQ-4.5, 74-REQ-4.E1,
                  74-REQ-4.E2
    """
    from agent_fox.session.convergence import converge_skeptic_records

    # Log warnings for failed instances
    warn_failed_parse_instances(raw_results, archetype="skeptic", run_id=run_id)

    filtered = [r for r in raw_results if r is not None]

    if not filtered:
        # 74-REQ-4.E1: All instances failed
        emit_audit_event(
            sink,
            run_id,
            AuditEventType.REVIEW_PARSE_FAILURE,
            node_id=node_id,
            archetype="skeptic",
            severity=AuditSeverity.WARNING,
            payload={"raw_output": "", "all_instances_failed": True},
        )
        return []

    merged, blocked = converge_skeptic_records(filtered, block_threshold)
    return merged, blocked
