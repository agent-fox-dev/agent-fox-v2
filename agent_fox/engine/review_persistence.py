"""Post-session review finding persistence.

Extracted from session_lifecycle.py to reduce the NodeSessionRunner
god class. Handles parsing and persisting structured findings from
review archetypes (reviewer with modes, verifier).

Requirements: 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1,
              74-REQ-3.*, 74-REQ-4.*, 74-REQ-5.*,
              98-REQ-5.1, 98-REQ-5.2
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_fox.core.json_extraction import extract_json_array
from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.knowledge.audit import AuditEventType, AuditSeverity
from agent_fox.knowledge.sink import SessionSink, SinkDispatcher

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


def _emit_persistence_event(
    sink: SinkDispatcher | SessionSink | None,
    run_id: str,
    archetype: str,
    node_id: str,
    spec_name: str,
    task_group: str,
    records: list[Any],
    count: int,
    *,
    mode: str | None = None,
) -> None:
    """Emit the appropriate persistence audit event after successful insertion.

    Logs a warning and continues if emission fails (84-REQ-2.E1).

    Requirements: 84-REQ-2.1, 84-REQ-2.2, 84-REQ-2.3, 84-REQ-2.E1
    """
    try:
        # Determine the effective dispatch key for reviewer modes
        dispatch_key = archetype
        if archetype == "reviewer" and mode:
            dispatch_key = f"reviewer:{mode}"

        if dispatch_key in ("skeptic", "reviewer:pre-review"):
            severity_summary: dict[str, int] = {}
            for r in records:
                sev = r.severity
                severity_summary[sev] = severity_summary.get(sev, 0) + 1
            emit_audit_event(
                sink,
                run_id,
                AuditEventType.REVIEW_FINDINGS_PERSISTED,
                node_id=node_id,
                archetype=archetype,
                payload={
                    "archetype": archetype,
                    "mode": mode,
                    "count": count,
                    "severity_summary": severity_summary,
                    "spec_name": spec_name,
                    "task_group": task_group,
                },
            )
        elif dispatch_key == "verifier":
            pass_count = sum(1 for r in records if r.verdict == "PASS")
            fail_count = sum(1 for r in records if r.verdict == "FAIL")
            emit_audit_event(
                sink,
                run_id,
                AuditEventType.REVIEW_VERDICTS_PERSISTED,
                node_id=node_id,
                archetype=archetype,
                payload={
                    "archetype": archetype,
                    "count": count,
                    "pass_count": pass_count,
                    "fail_count": fail_count,
                    "spec_name": spec_name,
                    "task_group": task_group,
                },
            )
        elif dispatch_key in ("oracle", "reviewer:drift-review"):
            severity_summary = {}
            for r in records:
                sev = r.severity
                severity_summary[sev] = severity_summary.get(sev, 0) + 1
            emit_audit_event(
                sink,
                run_id,
                AuditEventType.REVIEW_DRIFT_PERSISTED,
                node_id=node_id,
                archetype=archetype,
                payload={
                    "archetype": archetype,
                    "mode": mode,
                    "count": count,
                    "severity_summary": severity_summary,
                    "spec_name": spec_name,
                    "task_group": task_group,
                },
            )
    except Exception:
        logger.warning(
            "Failed to emit persistence audit event for %s %s",
            archetype,
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
    mode: str | None = None,
    specs_dir: Path | None = None,
) -> None:
    """Parse and persist structured findings from review archetypes.

    Uses extract_json_array to extract JSON from archetype output, then
    routes to the correct typed parser and insert function based on
    archetype and mode:
    - reviewer (pre-review)   -> parse_review_findings   -> insert_findings
    - reviewer (drift-review) -> parse_drift_findings    -> insert_drift_findings
    - reviewer (audit-review) -> parse_auditor_output    -> persist_auditor_results
    - skeptic  -> parse_review_findings   -> insert_findings (legacy)
    - verifier -> parse_verification_results -> insert_verdicts
    - oracle   -> parse_drift_findings    -> insert_drift_findings (legacy)

    Non-review archetypes (coder, etc.) are silently skipped.

    When initial extraction fails and session_handle is alive, a single
    format retry is attempted by appending a user message requesting
    corrected JSON output (74-REQ-3.*).

    Requirements: 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1,
                  53-REQ-1.E1, 53-REQ-2.E1, 53-REQ-3.E1,
                  74-REQ-3.1, 74-REQ-3.2, 74-REQ-3.3, 74-REQ-3.4,
                  74-REQ-3.5, 74-REQ-3.E1, 74-REQ-3.E2,
                  74-REQ-5.1, 74-REQ-5.2, 74-REQ-5.3,
                  98-REQ-5.1, 98-REQ-5.2
    """
    if archetype not in ("skeptic", "verifier", "oracle", "auditor", "reviewer"):
        return

    # Route reviewer archetype by mode to the correct persistence path
    if archetype == "reviewer":
        if mode == "audit-review":
            # Auditor convergence path — same as legacy "auditor"
            archetype = "auditor"
        elif mode in ("pre-review", "drift-review"):
            pass  # handled below in the dispatch table
        elif mode == "fix-review":
            # fix-review produces verdicts handled by the fix pipeline, not here
            return
        else:
            # Unknown reviewer mode — skip silently
            return

    session_id = f"{node_id}:{attempt}"
    tg = str(task_group)

    # Determine effective dispatch key for reviewer modes
    dispatch_key = archetype
    if archetype == "reviewer" and mode:
        if mode == "pre-review":
            dispatch_key = "skeptic"  # same parser/inserter as legacy skeptic
        elif mode == "drift-review":
            dispatch_key = "oracle"  # same parser/inserter as legacy oracle

    try:
        if dispatch_key in ("skeptic", "verifier", "oracle"):
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

            from agent_fox.knowledge.review_store import (
                insert_drift_findings,
                insert_findings,
                insert_verdicts,
            )
            from agent_fox.session.review_parser import (
                parse_drift_findings,
                parse_review_findings,
                parse_verification_results,
            )

            # Dispatch table: dispatch_key -> (parser, inserter, label)
            _review_dispatch: dict[str, tuple[Any, Any, str]] = {
                "skeptic": (
                    parse_review_findings,
                    insert_findings,
                    "review findings",
                ),
                "verifier": (
                    parse_verification_results,
                    insert_verdicts,
                    "verifier verdicts",
                ),
                "oracle": (
                    parse_drift_findings,
                    insert_drift_findings,
                    "drift findings",
                ),
            }
            parser, inserter, label = _review_dispatch[dispatch_key]
            records = parser(json_objects, spec_name, tg, session_id)
            if records:
                count = inserter(knowledge_db_conn, records)
                logger.info("Persisted %d %s for %s", count, label, node_id)
                _emit_persistence_event(
                    sink,
                    run_id,
                    archetype,
                    node_id,
                    spec_name,
                    tg,
                    records,
                    count,
                    mode=mode,
                )
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
            retry_attempted = False

            if audit_result is None:
                # Attempt format retry if session is still alive (mirrors 74-REQ-3.1)
                session_is_alive = session_handle is not None and getattr(session_handle, "is_alive", False)

                if session_is_alive:
                    logger.warning(
                        "Initial auditor parse failed for %s — attempting format retry",
                        node_id,
                    )
                    retry_response = session_handle.append_user_message(FORMAT_RETRY_PROMPT)
                    retry_attempted = True
                    audit_result = parse_auditor_output(retry_response)

                if audit_result is None:
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

            if specs_dir is not None:
                spec_dir = specs_dir / spec_name
            else:
                from agent_fox.core.config import AgentFoxConfig, resolve_spec_root

                spec_dir = resolve_spec_root(AgentFoxConfig(), Path.cwd()) / spec_name
            persist_auditor_results(spec_dir, audit_result, attempt=attempt, project_root=Path.cwd())

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
