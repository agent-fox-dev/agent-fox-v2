"""Knowledge base compaction: dedup and supersession resolution.

Reads from DuckDB, deduplicates, resolves supersession chains,
updates DuckDB (deletes removed facts), then exports to JSONL.

Requirements: 05-REQ-5.1, 05-REQ-5.2, 05-REQ-5.3, 05-REQ-5.E1,
              05-REQ-5.E2, 40-REQ-11.5
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

from agent_fox.core.models import content_hash
from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.store import load_all_facts

if TYPE_CHECKING:
    from agent_fox.knowledge.sink import SinkDispatcher

logger = logging.getLogger("agent_fox.knowledge.compaction")


def compact(
    conn: duckdb.DuckDBPyConnection,
    path: Path | None = None,
    *,
    sink_dispatcher: SinkDispatcher | None = None,
    run_id: str = "",
) -> tuple[int, int]:
    """Compact the knowledge base by removing duplicates and superseded facts.

    Steps:
    1. Load all non-superseded facts from DuckDB.
    2. Deduplicate by content hash (SHA-256 of content string), keeping the
       earliest instance.
    3. Resolve supersession chains: if B supersedes A and C supersedes B,
       only C survives.
    4. Update DuckDB (mark removed facts as superseded).
    5. Export surviving facts to JSONL.

    Args:
        path: Path to the JSONL file.
        sink_dispatcher: Optional sink to emit fact.compacted audit event.
        run_id: Run identifier for audit events.

    Returns:
        A tuple of (original_count, surviving_count).

    Requirements: 39-REQ-3.3
    """
    # Count ALL facts (including superseded) for the original count
    total_row = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()
    original_count = total_row[0] if total_row else 0

    # Load only non-superseded facts for processing
    facts = load_all_facts(conn)

    if original_count == 0 and not facts:
        logger.info("No compaction needed: knowledge base is empty.")
        return (0, 0)

    surviving = _deduplicate_by_content(facts)
    # 113-REQ-5.1: Substring supersession after content-hash dedup
    surviving, _substr_count = _substring_supersede(surviving)
    surviving = _resolve_supersession(surviving)

    surviving_count = len(surviving)
    superseded_count = original_count - surviving_count

    # Step 4: Mark removed facts as superseded in DuckDB
    surviving_ids = {f.id for f in surviving}
    removed_ids = [f.id for f in facts if f.id not in surviving_ids]
    if removed_ids:
        placeholders = ", ".join("?::UUID" for _ in removed_ids)
        conn.execute(
            f"UPDATE memory_facts SET superseded_by = id WHERE id IN ({placeholders})",
            removed_ids,
        )

    logger.info(
        "Compacted knowledge base: %d -> %d facts.",
        original_count,
        surviving_count,
    )

    # 113-REQ-5.E1: Log info when compaction reduces facts by more than 50%
    if original_count > 0 and surviving_count < original_count * 0.5:
        logger.info(
            "Large compaction: reduced from %d to %d facts (>50%% reduction)",
            original_count,
            surviving_count,
        )

    # 40-REQ-11.5: Emit fact.compacted audit event
    if sink_dispatcher is not None and run_id:
        try:
            from agent_fox.knowledge.audit import AuditEvent, AuditEventType

            event = AuditEvent(
                run_id=run_id,
                event_type=AuditEventType.FACT_COMPACTED,
                payload={
                    "facts_before": original_count,
                    "facts_after": surviving_count,
                    "superseded_count": superseded_count,
                },
            )
            sink_dispatcher.emit_audit_event(event)
        except Exception:
            logger.debug("Failed to emit fact.compacted audit event", exc_info=True)

    return (original_count, surviving_count)


def _substring_supersede(
    facts: list[Fact],
) -> tuple[list[Fact], int]:
    """Identify facts whose content is a substring of another fact with equal
    or higher confidence. Mark the shorter fact as superseded by the longer.

    Returns (surviving_facts, superseded_count).

    Requirements: 113-REQ-5.1
    """
    superseded_ids: set[str] = set()

    for i, fact_a in enumerate(facts):
        if fact_a.id in superseded_ids:
            continue
        for j, fact_b in enumerate(facts):
            if i == j or fact_b.id in superseded_ids:
                continue
            # Check if fact_a's content is a substring of fact_b's content
            if fact_a.content in fact_b.content and fact_a.content != fact_b.content:
                # fact_a is substring of fact_b; supersede fact_a only if
                # fact_b has equal or higher confidence
                if fact_b.confidence >= fact_a.confidence:
                    superseded_ids.add(fact_a.id)
                    break

    surviving = [f for f in facts if f.id not in superseded_ids]
    return surviving, len(superseded_ids)


def _content_hash(content: str) -> str:
    """Compute SHA-256 hash of a fact's content string."""
    return content_hash(content)


def _deduplicate_by_content(facts: list[Fact]) -> list[Fact]:
    """Remove duplicate facts with the same content hash.

    Keeps the fact with highest confidence for each unique hash.
    Ties are broken by recency (more recent wins).

    Requirements: 113-REQ-5.3
    """
    # Group facts by content hash, keeping the best for each.
    best: dict[str, Fact] = {}
    for fact in facts:
        h = _content_hash(fact.content)
        if h not in best:
            best[h] = fact
        else:
            existing = best[h]
            # Higher confidence wins; ties broken by recency (later created_at)
            if (fact.confidence > existing.confidence) or (
                fact.confidence == existing.confidence
                and fact.created_at > existing.created_at
            ):
                best[h] = fact

    # Preserve original ordering among the surviving facts.
    seen_hashes: set[str] = set()
    result: list[Fact] = []
    for fact in facts:
        h = _content_hash(fact.content)
        if h not in seen_hashes and best[h].id == fact.id:
            result.append(fact)
            seen_hashes.add(h)
    return result


def _resolve_supersession(facts: list[Fact]) -> list[Fact]:
    """Remove facts that have been superseded by newer facts.

    A fact is superseded if another fact references its ID in the
    `supersedes` field. Chains are resolved transitively.
    """
    # Build set of all IDs that are superseded by another fact.
    superseded_ids: set[str] = set()
    for fact in facts:
        if fact.supersedes is not None:
            superseded_ids.add(fact.supersedes)

    return [f for f in facts if f.id not in superseded_ids]
