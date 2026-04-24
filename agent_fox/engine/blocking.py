"""Review-blocking evaluation: decides whether review findings block downstream tasks.

Extracted from result_handler.py to isolate blocking decision logic.

Requirements: 26-REQ-9.3, 30-REQ-2.3, 84-REQ-3.1, 84-REQ-3.E1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agent_fox.core.config import ArchetypesConfig
from agent_fox.core.node_id import parse_node_id
from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.engine.state import SessionRecord
from agent_fox.knowledge.audit import AuditEventType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BlockDecision:
    """Result of evaluating whether a review session should block a task."""

    should_block: bool
    coder_node_id: str = ""
    reason: str = ""


def _format_block_reason(
    archetype: str,
    findings: list[Any],
    threshold: int,
    spec_name: str,
    task_group: str,
) -> str:
    """Format an enriched blocking reason string with finding IDs and descriptions.

    Includes the count of critical findings, up to 3 finding IDs as `F-<8hex>`
    short prefixes, truncated descriptions (max 60 chars each), and "and N more"
    when there are more than 3 critical findings.

    Requirements: 84-REQ-3.1, 84-REQ-3.E1
    """
    critical_findings = [f for f in findings if f.severity.lower() == "critical"]
    n = len(critical_findings)

    header = (
        f"{archetype.capitalize()} found {n} critical finding(s) (threshold: {threshold}) for {spec_name}:{task_group}"
    )

    if n == 0:
        return header

    shown = critical_findings[:3]
    parts = []
    for finding in shown:
        # Build F-<8hex> short ID from the UUID
        raw_id = finding.id.replace("-", "")[:8]
        short_id = f"F-{raw_id}"
        desc = finding.description[:60]
        if len(finding.description) > 60:
            desc += "…"
        parts.append(f"{short_id}: {desc}")

    detail = ", ".join(parts)
    if n > 3:
        detail += f", and {n - 3} more"

    return f"{header} — {detail}"


def evaluate_review_blocking(
    record: SessionRecord,
    archetypes_config: ArchetypesConfig | None,
    knowledge_db_conn: Any | None,
    *,
    mode: str | None = None,
    sink: Any | None = None,
    run_id: str = "",
) -> BlockDecision:
    """Evaluate whether a reviewer session should block its downstream task.

    Supports the consolidated reviewer archetype with modes (pre-review,
    drift-review) as well as legacy archetype names for backward compat.

    Queries persisted review findings from DuckDB, counts critical findings,
    applies the configured (or learned) block threshold.

    Critical findings with category='security' always trigger blocking,
    regardless of the numeric threshold, because security vulnerabilities
    must be remediated before downstream work can proceeded.

    Returns a BlockDecision indicating whether blocking should occur and why.
    """
    archetype = record.archetype

    # Only reviewer pre-review and drift-review modes can block.
    # Audit-review and fix-review do not participate in blocking.
    if archetype == "reviewer":
        if mode not in ("pre-review", "drift-review"):
            return BlockDecision(should_block=False)
    elif archetype not in ("skeptic", "oracle"):
        # Legacy names kept for backward compat with old session records
        return BlockDecision(should_block=False)

    if knowledge_db_conn is None:
        return BlockDecision(should_block=False)

    parsed = parse_node_id(record.node_id)
    spec_name = parsed.spec_name
    # Group-0 nodes are auto_pre reviewers; the first coder group is always 1
    task_group = "1" if parsed.group_number == 0 else str(parsed.group_number)
    coder_node_id = f"{spec_name}:{task_group}"

    # Display label for log messages
    display_name = f"reviewer:{mode}" if archetype == "reviewer" and mode else archetype

    try:
        from agent_fox.knowledge.review_store import query_findings_by_session

        session_id = f"{record.node_id}:{record.attempt}"
        findings = query_findings_by_session(knowledge_db_conn, session_id)

        # Scope findings to this task_group only — cross-group findings (e.g. from
        # a spec-wide reviewer session) must not block an unrelated coder group.
        findings = [f for f in findings if f.task_group == task_group]

        critical_count = sum(1 for f in findings if f.severity.lower() == "critical")

        if critical_count == 0:
            return BlockDecision(should_block=False)

        # Security bypass: critical findings with category='security' always block,
        # regardless of the numeric threshold.
        security_critical = [
            f for f in findings if f.severity.lower() == "critical" and getattr(f, "category", None) == "security"
        ]
        if security_critical:
            shown = security_critical[:3]
            detail = ", ".join(
                f"F-{f.id.replace('-', '')[:8]}: {f.description[:60]}" + ("…" if len(f.description) > 60 else "")
                for f in shown
            )
            reason = (
                f"[SECURITY] {display_name.capitalize()} found {len(security_critical)} critical "
                f"security finding(s) for {spec_name}:{task_group} — {detail}"
            )
            logger.warning("SECURITY blocking %s: %s", coder_node_id, reason)
            emit_audit_event(
                sink,
                run_id,
                AuditEventType.SECURITY_FINDING_BLOCKED,
                node_id=record.node_id,
                session_id=session_id,
                archetype=archetype,
                payload={
                    "spec_name": spec_name,
                    "task_group": task_group,
                    "security_critical_count": len(security_critical),
                    "finding_ids": [str(f.id) for f in security_critical],
                },
            )
            return BlockDecision(
                should_block=True,
                coder_node_id=coder_node_id,
                reason=reason,
            )

        # Resolve threshold from ReviewerConfig by mode (or legacy archetype name)
        configured_threshold = 3  # conservative default
        if archetypes_config is not None:
            rc = archetypes_config.reviewer_config
            if archetype == "reviewer":
                if mode == "pre-review":
                    configured_threshold = rc.pre_review_block_threshold
                elif mode == "drift-review":
                    if rc.drift_review_block_threshold is None:
                        return BlockDecision(should_block=False)
                    configured_threshold = rc.drift_review_block_threshold
            elif archetype == "skeptic":
                configured_threshold = rc.pre_review_block_threshold
            elif archetype == "oracle":
                if rc.drift_review_block_threshold is None:
                    return BlockDecision(should_block=False)
                configured_threshold = rc.drift_review_block_threshold

        blocked = critical_count >= configured_threshold

        if blocked:
            reason = _format_block_reason(
                display_name,
                findings,
                configured_threshold,
                spec_name,
                task_group,
            )
            logger.warning(
                "%s blocking %s: %s",
                display_name.capitalize(),
                coder_node_id,
                reason,
            )
            return BlockDecision(
                should_block=True,
                coder_node_id=coder_node_id,
                reason=reason,
            )

    except Exception:
        logger.warning(
            "Failed to evaluate %s blocking for %s",
            display_name,
            record.node_id,
            exc_info=True,
        )

    return BlockDecision(should_block=False)
