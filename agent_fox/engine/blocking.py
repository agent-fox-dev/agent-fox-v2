"""Skeptic/oracle blocking logic: review-gated task blocking.

Extracted from engine.py to reduce the Orchestrator class size.
Evaluates whether a skeptic or oracle review session's findings
should block the downstream coder task.

Requirements: 26-REQ-9.3, 30-REQ-2.3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agent_fox.core.config import ArchetypesConfig
from agent_fox.core.node_id import parse_node_id
from agent_fox.engine.state import SessionRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BlockDecision:
    """Result of evaluating whether a review session should block a task."""

    should_block: bool
    coder_node_id: str = ""
    reason: str = ""


def evaluate_review_blocking(
    record: SessionRecord,
    archetypes_config: ArchetypesConfig | None,
    knowledge_db_conn: Any | None,
) -> BlockDecision:
    """Evaluate whether a skeptic/oracle session should block its downstream task.

    Queries persisted review findings from DuckDB, counts critical findings,
    applies the configured (or learned) block threshold.

    Returns a BlockDecision indicating whether blocking should occur and why.
    """
    archetype = record.archetype
    if archetype not in ("skeptic", "oracle"):
        return BlockDecision(should_block=False)

    if knowledge_db_conn is None:
        return BlockDecision(should_block=False)

    parsed = parse_node_id(record.node_id)
    spec_name = parsed.spec_name
    task_group = str(parsed.group_number) if parsed.group_number else "1"
    coder_node_id = f"{spec_name}:{task_group}"

    try:
        from agent_fox.knowledge.review_store import query_findings_by_session

        session_id = f"{record.node_id}:{record.attempt}"
        findings = query_findings_by_session(knowledge_db_conn, session_id)

        critical_count = sum(1 for f in findings if f.severity.lower() == "critical")

        if critical_count == 0:
            return BlockDecision(should_block=False)

        # Resolve threshold
        if archetype == "skeptic" and archetypes_config is not None:
            configured_threshold = archetypes_config.skeptic_config.block_threshold
        elif archetype == "oracle" and archetypes_config is not None:
            configured_threshold = archetypes_config.oracle_settings.block_threshold
            if configured_threshold is None:
                # Oracle is advisory-only when block_threshold is None
                return BlockDecision(should_block=False)
        else:
            # No config available, use conservative default
            configured_threshold = 3

        from agent_fox.session.convergence import resolve_block_threshold

        effective_threshold = resolve_block_threshold(
            configured_threshold,
            archetype,
            knowledge_db_conn,
            learn_thresholds=False,
        )

        blocked = critical_count > effective_threshold

        # Record the blocking decision for threshold learning
        try:
            from agent_fox.knowledge.blocking_history import (
                BlockingDecision as HistoryDecision,
            )
            from agent_fox.knowledge.blocking_history import (
                record_blocking_decision,
            )

            decision = HistoryDecision(
                spec_name=spec_name,
                archetype=archetype,
                critical_count=critical_count,
                threshold=effective_threshold,
                blocked=blocked,
                outcome="",  # outcome assessed later
            )
            record_blocking_decision(knowledge_db_conn, decision)
        except Exception:
            logger.debug(
                "Failed to record blocking decision for %s",
                record.node_id,
                exc_info=True,
            )

        if blocked:
            reason = (
                f"{archetype.capitalize()} found {critical_count} critical "
                f"finding(s) (threshold: {effective_threshold}) for "
                f"{spec_name}:{task_group}"
            )
            logger.warning(
                "%s blocking %s: %s",
                archetype.capitalize(),
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
            archetype,
            record.node_id,
            exc_info=True,
        )

    return BlockDecision(should_block=False)
