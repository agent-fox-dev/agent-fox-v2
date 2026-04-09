"""Fact lifecycle management: dedup, contradiction detection, decay cleanup.

Provides automated mechanisms to combat knowledge staleness:
- Embedding-based deduplication on ingestion
- LLM-powered contradiction detection
- Age-based confidence decay with auto-supersession

Requirements: 90-REQ-1.*, 90-REQ-2.*, 90-REQ-3.*, 90-REQ-4.*
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from agent_fox.core.config import KnowledgeConfig
    from agent_fox.knowledge.facts import Fact
    from agent_fox.knowledge.sink import SinkDispatcher

logger = logging.getLogger("agent_fox.knowledge.lifecycle")


@dataclass(frozen=True)
class DedupResult:
    """Result of embedding-based deduplication."""

    superseded_ids: list[str] = field(default_factory=list)
    surviving_facts: list[Fact] = field(default_factory=list)


@dataclass(frozen=True)
class ContradictionVerdict:
    """LLM verdict on whether two facts contradict."""

    new_fact_id: str = ""
    old_fact_id: str = ""
    contradicts: bool = False
    reason: str = ""


@dataclass(frozen=True)
class ContradictionResult:
    """Result of contradiction detection."""

    superseded_ids: list[str] = field(default_factory=list)
    verdicts: list[ContradictionVerdict] = field(default_factory=list)


@dataclass(frozen=True)
class CleanupResult:
    """Summary of end-of-run cleanup."""

    facts_expired: int = 0
    facts_deduped: int = 0
    facts_contradicted: int = 0
    active_facts_remaining: int = 0


def dedup_new_facts(
    conn: duckdb.DuckDBPyConnection,
    new_facts: list[Fact],
    threshold: float = 0.92,
) -> DedupResult:
    """Check new facts against existing actives for near-duplicates.

    For each new fact that has an embedding, query all active existing facts
    (those not in the new_facts set) for cosine similarity above *threshold*.
    Any existing fact above the threshold is superseded by the new fact.

    Requirements: 90-REQ-1.1, 90-REQ-1.2, 90-REQ-1.3, 90-REQ-1.5
    """
    if not new_facts:
        return DedupResult()

    new_ids = {f.id for f in new_facts}
    all_superseded: list[str] = []
    surviving: list[Fact] = []

    for new_fact in new_facts:
        # Check if the new fact has an embedding (90-REQ-1.E1)
        emb_row = conn.execute(
            "SELECT embedding FROM memory_embeddings WHERE CAST(id AS VARCHAR) = ?",
            [new_fact.id],
        ).fetchone()

        if emb_row is None:
            # No embedding for this new fact — skip dedup
            surviving.append(new_fact)
            continue

        # Check if any existing (non-new) active facts have embeddings (90-REQ-1.E2)
        # Build placeholders for the new fact IDs to exclude
        placeholders = ", ".join(f"'{nid}'" for nid in new_ids)
        # Query for existing active facts with cosine similarity above threshold
        # DuckDB VSS: array_cosine_distance returns distance (1 - similarity)
        # So similarity = 1 - distance, and we want similarity >= threshold
        # => distance <= 1 - threshold
        max_distance = 1.0 - threshold

        try:
            rows = conn.execute(
                f"""
                SELECT CAST(mf.id AS VARCHAR),
                       array_cosine_distance(me.embedding, ne.embedding) AS dist
                FROM memory_facts mf
                JOIN memory_embeddings me ON mf.id = me.id
                CROSS JOIN (
                    SELECT embedding FROM memory_embeddings
                    WHERE CAST(id AS VARCHAR) = ?
                ) ne
                WHERE mf.superseded_by IS NULL
                  AND CAST(mf.id AS VARCHAR) NOT IN ({placeholders})
                  AND array_cosine_distance(me.embedding, ne.embedding) <= ?
                """,
                [new_fact.id, max_distance],
            ).fetchall()
        except duckdb.Error:
            # If query fails (e.g., no embeddings exist), skip dedup
            surviving.append(new_fact)
            continue

        if rows:
            superseded_ids = [row[0] for row in rows]
            for old_id in superseded_ids:
                conn.execute(
                    "UPDATE memory_facts SET superseded_by = ?::UUID "
                    "WHERE CAST(id AS VARCHAR) = ?",
                    [new_fact.id, old_id],
                )
            all_superseded.extend(superseded_ids)
            logger.info(
                "Dedup: superseded %d fact(s) %s with new fact %s",
                len(superseded_ids),
                superseded_ids,
                new_fact.id,
            )

        surviving.append(new_fact)

    return DedupResult(superseded_ids=all_superseded, surviving_facts=surviving)


def detect_contradictions(
    conn: duckdb.DuckDBPyConnection,
    new_facts: list[Fact],
    *,
    threshold: float = 0.8,
    model: str = "SIMPLE",
) -> ContradictionResult:
    """Identify and resolve contradictions between new and existing facts.

    Requirements: 90-REQ-2.1, 90-REQ-2.2, 90-REQ-2.3, 90-REQ-2.4, 90-REQ-2.6
    """
    from agent_fox.knowledge.contradiction import classify_contradiction_batch
    from agent_fox.knowledge.facts import Fact as FactType

    if not new_facts:
        return ContradictionResult()

    new_ids = {f.id for f in new_facts}
    all_superseded: list[str] = []
    all_verdicts: list[ContradictionVerdict] = []

    # Collect candidate pairs: (new_fact, existing_fact) with similarity above threshold
    candidate_pairs: list[tuple[FactType, FactType]] = []

    for new_fact in new_facts:
        # Check if new fact has embedding (90-REQ-2.E2)
        emb_row = conn.execute(
            "SELECT embedding FROM memory_embeddings WHERE CAST(id AS VARCHAR) = ?",
            [new_fact.id],
        ).fetchone()

        if emb_row is None:
            continue

        max_distance = 1.0 - threshold
        placeholders = ", ".join(f"'{nid}'" for nid in new_ids)

        try:
            rows = conn.execute(
                f"""
                SELECT CAST(mf.id AS VARCHAR), mf.content, mf.category,
                       mf.spec_name, mf.confidence, mf.created_at,
                       mf.session_id, mf.commit_sha
                FROM memory_facts mf
                JOIN memory_embeddings me ON mf.id = me.id
                CROSS JOIN (
                    SELECT embedding FROM memory_embeddings
                    WHERE CAST(id AS VARCHAR) = ?
                ) ne
                WHERE mf.superseded_by IS NULL
                  AND CAST(mf.id AS VARCHAR) NOT IN ({placeholders})
                  AND array_cosine_distance(me.embedding, ne.embedding) <= ?
                """,
                [new_fact.id, max_distance],
            ).fetchall()
        except duckdb.Error:
            continue

        for row in rows:
            from agent_fox.knowledge.facts import parse_confidence

            old_fact = FactType(
                id=str(row[0]),
                content=row[1] or "",
                category=row[2] or "pattern",
                spec_name=row[3] or "",
                keywords=[],
                confidence=parse_confidence(row[4]),
                created_at=str(row[5]) if row[5] else "",
                session_id=row[6],
                commit_sha=row[7],
            )
            candidate_pairs.append((new_fact, old_fact))

    if not candidate_pairs:
        return ContradictionResult()

    # Process in batches of 10 (90-REQ-2.5)
    batch_size = 10
    for i in range(0, len(candidate_pairs), batch_size):
        batch = candidate_pairs[i : i + batch_size]

        try:
            result_or_coro = classify_contradiction_batch(batch, model=model)
            # classify_contradiction_batch is async; run the coroutine
            if asyncio.iscoroutine(result_or_coro):
                verdicts = asyncio.run(result_or_coro)
            else:
                verdicts = result_or_coro  # type: ignore[assignment]
        except Exception:
            logger.warning(
                "Contradiction classification failed for batch %d; skipping",
                i // batch_size,
                exc_info=True,
            )
            continue

        for verdict in verdicts:
            cv = ContradictionVerdict(
                new_fact_id=verdict.new_fact_id,
                old_fact_id=verdict.old_fact_id,
                contradicts=verdict.contradicts,
                reason=verdict.reason,
            )
            all_verdicts.append(cv)

            if verdict.contradicts:
                conn.execute(
                    "UPDATE memory_facts SET superseded_by = ?::UUID "
                    "WHERE CAST(id AS VARCHAR) = ?",
                    [verdict.new_fact_id, verdict.old_fact_id],
                )
                all_superseded.append(verdict.old_fact_id)
                logger.info(
                    "Contradiction: superseded fact %s with %s — %s",
                    verdict.old_fact_id,
                    verdict.new_fact_id,
                    verdict.reason,
                )

    return ContradictionResult(
        superseded_ids=all_superseded, verdicts=all_verdicts
    )


def run_decay_cleanup(
    conn: duckdb.DuckDBPyConnection,
    *,
    half_life_days: float = 90.0,
    decay_floor: float = 0.1,
) -> int:
    """Apply age-based decay and auto-supersede expired facts.

    Computes effective confidence for each active fact:
        effective = stored_confidence * (0.5 ^ (age_days / half_life_days))

    Facts whose effective confidence falls below *decay_floor* are
    self-superseded (superseded_by = id).

    The stored ``confidence`` column is never modified (90-REQ-3.6).

    Requirements: 90-REQ-3.1, 90-REQ-3.2, 90-REQ-3.5, 90-REQ-3.6
    """
    now = datetime.now(UTC)

    # Load all active facts with their timestamps and confidence
    rows = conn.execute(
        "SELECT CAST(id AS VARCHAR), confidence, created_at "
        "FROM memory_facts WHERE superseded_by IS NULL"
    ).fetchall()

    expired_count = 0
    for row in rows:
        fact_id = row[0]
        confidence = row[1]
        created_at = row[2]

        # Handle NULL/unparseable created_at (90-REQ-3.E1)
        if created_at is None:
            logger.warning(
                "Fact %s has NULL created_at; skipping decay", fact_id
            )
            continue

        # Parse created_at to datetime if needed
        if isinstance(created_at, str):
            try:
                ts = datetime.fromisoformat(created_at)
            except (ValueError, TypeError):
                logger.warning(
                    "Fact %s has unparseable created_at '%s'; skipping decay",
                    fact_id,
                    created_at,
                )
                continue
        elif isinstance(created_at, datetime):
            ts = created_at
        else:
            logger.warning(
                "Fact %s has unexpected created_at type %s; skipping decay",
                fact_id,
                type(created_at).__name__,
            )
            continue

        # Ensure timezone-aware comparison
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)

        # Compute age in days (90-REQ-3.E2: future dates get zero decay)
        age_seconds = (now - ts).total_seconds()
        age_days = max(0.0, age_seconds / 86400.0)

        # Parse confidence
        try:
            conf = float(confidence)
        except (TypeError, ValueError):
            from agent_fox.knowledge.facts import parse_confidence

            conf = parse_confidence(confidence)

        # Compute effective confidence (90-REQ-3.1)
        effective = conf * (0.5 ** (age_days / half_life_days))

        # Auto-supersede if below floor (90-REQ-3.2)
        if effective < decay_floor:
            conn.execute(
                "UPDATE memory_facts SET superseded_by = id "
                "WHERE CAST(id AS VARCHAR) = ?",
                [fact_id],
            )
            expired_count += 1

    if expired_count > 0:
        logger.info("Decay cleanup: auto-superseded %d fact(s)", expired_count)

    return expired_count


def run_cleanup(
    conn: duckdb.DuckDBPyConnection,
    config: KnowledgeConfig,
    *,
    sink_dispatcher: SinkDispatcher | None = None,
    run_id: str = "",
) -> CleanupResult:
    """Full cleanup: decay + audit event. Called at end-of-run.

    1. Check cleanup_enabled config (90-REQ-4.E1)
    2. Check active fact count against threshold (90-REQ-4.2)
    3. Run decay if above threshold
    4. Emit fact.cleanup audit event (90-REQ-4.5)
    5. Return CleanupResult (90-REQ-4.6)

    Requirements: 90-REQ-4.1, 90-REQ-4.2, 90-REQ-4.5, 90-REQ-4.6
    """
    # Check if cleanup is enabled (90-REQ-4.E1)
    if not config.cleanup_enabled:
        logger.debug("Fact lifecycle cleanup disabled via config")
        return CleanupResult()

    facts_expired = 0

    try:
        # Count active facts
        active_count = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
        ).fetchone()[0]

        # Only run decay if above threshold (90-REQ-4.2, 90-REQ-4.3)
        if active_count > config.cleanup_fact_threshold:
            facts_expired = run_decay_cleanup(
                conn,
                half_life_days=config.decay_half_life_days,
                decay_floor=config.decay_floor,
            )

        # Recount active facts after cleanup
        active_remaining = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
        ).fetchone()[0]

    except duckdb.Error:
        logger.warning(
            "DuckDB unavailable during cleanup; skipping", exc_info=True
        )
        return CleanupResult()

    result = CleanupResult(
        facts_expired=facts_expired,
        facts_deduped=0,
        facts_contradicted=0,
        active_facts_remaining=active_remaining,
    )

    # Emit audit event (90-REQ-4.5)
    if sink_dispatcher is not None:
        from agent_fox.knowledge.audit import AuditEvent, AuditEventType

        event = AuditEvent(
            run_id=run_id,
            event_type=AuditEventType.FACT_CLEANUP,
            payload={
                "facts_expired": result.facts_expired,
                "facts_deduped": result.facts_deduped,
                "facts_contradicted": result.facts_contradicted,
                "active_facts_remaining": result.active_facts_remaining,
            },
        )
        sink_dispatcher.emit_audit_event(event)

    return result
