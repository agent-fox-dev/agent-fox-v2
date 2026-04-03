"""Context assembly: fact loading and causal enrichment for sessions.

Extracted from session_lifecycle.py to reduce the NodeSessionRunner
god class. Handles loading relevant memory facts, enriching with
causal context, and building retry context from prior review findings.

Requirements: 05-REQ-4.1, 05-REQ-4.2, 13-REQ-7.1, 42-REQ-3.2,
              53-REQ-5.1
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent_fox.engine.fact_cache import RankedFactCache, get_cached_facts
from agent_fox.knowledge.filtering import select_relevant_facts
from agent_fox.knowledge.store import load_all_facts
from agent_fox.session.context import select_context_with_causal

if TYPE_CHECKING:
    from agent_fox.knowledge.db import KnowledgeDB

logger = logging.getLogger(__name__)


def load_relevant_facts(
    knowledge_db: KnowledgeDB,
    spec_name: str,
    confidence_threshold: float,
    fact_cache: dict[str, RankedFactCache] | None = None,
) -> list:
    """Load relevant facts, using the pre-computed cache when available.

    When a valid cache entry exists for the current spec and the fact
    count has not changed since the cache was built, return cached facts
    directly. Otherwise fall back to live computation via
    select_relevant_facts().

    Requirements: 42-REQ-3.2, 42-REQ-3.3, 42-REQ-3.4
    """
    # 42-REQ-3.2: Try cache first when cache is available
    if fact_cache is not None:
        try:
            current_count: int = knowledge_db.connection.execute(
                "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
            ).fetchone()[0]
            cached = get_cached_facts(fact_cache, spec_name, current_count)
            if cached is not None:
                logger.debug(
                    "Using cached fact rankings for %s (%d facts)",
                    spec_name,
                    len(cached),
                )
                return cached
            # 42-REQ-3.3: Cache is stale or missing — fall through to live
            logger.debug(
                "Cache miss for %s (count mismatch or absent); falling back to live computation",
                spec_name,
            )
        except Exception:
            logger.debug(
                "Cache lookup failed for %s; falling back to live computation",
                spec_name,
                exc_info=True,
            )

    # Live computation (no cache, stale cache, or cache lookup failure)
    all_facts = load_all_facts(knowledge_db.connection)
    if not all_facts:
        return []
    return select_relevant_facts(
        all_facts,
        spec_name,
        task_keywords=[spec_name],
        confidence_threshold=confidence_threshold,
    )


def enhance_with_causal(
    knowledge_db: KnowledgeDB,
    spec_name: str,
    relevant_facts: list,
) -> list[str]:
    """Enhance keyword-selected facts with causal context.

    Uses select_context_with_causal() to augment the keyword-matched
    facts with causally-linked facts from the DuckDB knowledge store.

    Requirements: 13-REQ-7.1, 13-REQ-7.2, 38-REQ-2.1, 38-REQ-2.3
    """
    keyword_dicts = [
        {
            "id": f.id,
            "content": f.content,
            "spec_name": f.spec_name,
        }
        for f in relevant_facts
    ]

    enhanced = select_context_with_causal(
        knowledge_db.connection,
        spec_name,
        touched_files=[],
        keyword_facts=keyword_dicts,
    )
    return [f["content"] for f in enhanced]


def build_retry_context(
    knowledge_db: KnowledgeDB,
    spec_name: str,
) -> str:
    """Query active critical/major findings for the spec and format them.

    Returns a structured block for inclusion in coder retry prompts,
    listing all active critical and major review findings. Returns an
    empty string if no such findings exist or if the DB is unavailable.

    Requirements: 53-REQ-5.1, 53-REQ-5.2, 53-REQ-5.E1
    """
    try:
        from agent_fox.knowledge.review_store import query_active_findings

        conn = knowledge_db.connection
        findings = query_active_findings(conn, spec_name)
        critical_major = [f for f in findings if f.severity in ("critical", "major")]
        if not critical_major:
            return ""

        lines = [
            f"## Prior Review Findings for {spec_name}",
            "",
            "The following critical/major issues were identified in prior "
            "review sessions. Please address these in your implementation:",
            "",
        ]
        for finding in critical_major:
            ref_str = f" [{finding.requirement_ref}]" if finding.requirement_ref else ""
            lines.append(f"- **{finding.severity.upper()}**{ref_str}: {finding.description}")
        return "\n".join(lines)

    except Exception:
        logger.warning(
            "Failed to build retry context for %s, continuing without",
            spec_name,
            exc_info=True,
        )
        return ""
