"""Knowledge harvesting: extract facts and causal links from sessions.

Separated from session_lifecycle.py to isolate the LLM-powered knowledge
extraction concern from the session lifecycle orchestration.

Requirements: 05-REQ-1.1, 05-REQ-1.E1, 13-REQ-2.1, 13-REQ-2.2, 13-REQ-3.1,
              40-REQ-11.4, 52-REQ-1.1, 52-REQ-3.1, 52-REQ-3.2, 52-REQ-4.1,
              52-REQ-4.2, 52-REQ-4.E1, 52-REQ-5.1, 52-REQ-5.2
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agent_fox.core.token_tracker import track_response_usage
from agent_fox.knowledge.causal import store_causal_links
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.extraction import (
    enrich_extraction_with_causal,
    extract_facts,
    parse_causal_links,
)
from agent_fox.knowledge.store import load_all_facts

if TYPE_CHECKING:
    from agent_fox.knowledge.embeddings import EmbeddingGenerator
    from agent_fox.knowledge.sink import SinkDispatcher

logger = logging.getLogger(__name__)


async def extract_and_store_knowledge(
    transcript: str,
    spec_name: str,
    node_id: str,
    memory_extraction_model: str,
    knowledge_db: KnowledgeDB,
    *,
    sink_dispatcher: SinkDispatcher | None = None,
    run_id: str = "",
    embedder: EmbeddingGenerator | None = None,
    causal_context_limit: int = 200,
) -> None:
    """Extract facts and causal links from a session transcript.

    1. Calls the LLM to extract facts from the transcript.
    2. Writes facts to DuckDB via sync_facts_to_duckdb.
    3. Generates embeddings for new facts (best-effort).
    4. Checks fact threshold and extracts causal links if >= 5.
    5. Emits harvest.complete or harvest.empty audit events.

    Requirements: 05-REQ-1.1, 05-REQ-1.E1, 13-REQ-2.1, 13-REQ-2.2,
                  38-REQ-2.1, 38-REQ-2.3, 39-REQ-3.1,
                  52-REQ-3.1, 52-REQ-3.2, 52-REQ-4.1, 52-REQ-4.2,
                  52-REQ-4.E1, 52-REQ-5.1, 52-REQ-5.2
    """
    facts = await extract_facts(transcript, spec_name, memory_extraction_model, session_id=node_id)

    causal_link_count = 0

    if not facts:
        # 52-REQ-4.2: Emit harvest.empty when non-empty input yields zero facts
        if transcript:
            _emit_harvest_empty(sink_dispatcher, run_id, node_id)
        return

    sync_facts_to_duckdb(knowledge_db, facts)
    logger.info(
        "Extracted %d facts from session %s",
        len(facts),
        node_id,
    )

    # 52-REQ-3.1, 52-REQ-3.2: Generate embeddings (best-effort)
    _generate_embeddings(knowledge_db, facts, embedder)

    # 40-REQ-11.4: Emit fact.extracted audit event
    if sink_dispatcher is not None and run_id:
        try:
            from agent_fox.knowledge.audit import AuditEvent, AuditEventType

            categories = list({f.category for f in facts if hasattr(f, "category")})
            event = AuditEvent(
                run_id=run_id,
                event_type=AuditEventType.FACT_EXTRACTED,
                node_id=node_id,
                payload={
                    "fact_count": len(facts),
                    "categories": categories,
                },
            )
            sink_dispatcher.emit_audit_event(event)
        except Exception:
            logger.debug("Failed to emit fact.extracted audit event", exc_info=True)

    # 52-REQ-5.1, 52-REQ-5.2: Check minimum fact threshold for causal extraction
    non_superseded_count = _count_non_superseded_facts(knowledge_db)
    if non_superseded_count >= 5:
        causal_link_count = _extract_causal_links(
            facts,
            node_id,
            memory_extraction_model,
            knowledge_db,
            causal_context_limit=causal_context_limit,
            sink_dispatcher=sink_dispatcher,
            run_id=run_id,
        )
    else:
        logger.debug(
            "Skipping causal extraction: insufficient facts (%d < 5)",
            non_superseded_count,
        )

    # 52-REQ-4.1: Emit harvest.complete audit event
    _emit_harvest_complete(sink_dispatcher, run_id, node_id, facts, causal_link_count)


def _count_non_superseded_facts(knowledge_db: KnowledgeDB) -> int:
    """Count non-superseded facts in memory_facts.

    Requirements: 52-REQ-5.1, 52-REQ-5.2
    """
    row = knowledge_db.connection.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()
    return row[0] if row else 0


def _generate_embeddings(
    knowledge_db: KnowledgeDB,
    facts: list[Any],
    embedder: Any | None,
) -> None:
    """Generate and store embeddings for new facts (best-effort).

    If the embedder is None or embedding generation fails, log a warning
    and continue — fact storage is not blocked.

    Requirements: 52-REQ-3.1, 52-REQ-3.2, 52-REQ-3.E1
    """
    if embedder is None:
        return

    try:
        texts = [f.content for f in facts]
        embeddings = embedder.embed_batch(texts)
        conn = knowledge_db.connection
        dim = embedder.embedding_dimensions
        for fact, embedding in zip(facts, embeddings):
            if embedding is not None:
                try:
                    conn.execute(
                        f"INSERT OR IGNORE INTO memory_embeddings (id, embedding) VALUES (?::UUID, ?::FLOAT[{dim}])",
                        [fact.id, embedding],
                    )
                except Exception:
                    logger.warning(
                        "Failed to store embedding for fact %s",
                        fact.id,
                        exc_info=True,
                    )
    except Exception:
        logger.warning(
            "Embedding generation failed for batch of %d facts",
            len(facts),
            exc_info=True,
        )


def _emit_harvest_complete(
    sink_dispatcher: Any | None,
    run_id: str,
    node_id: str,
    facts: list[Any],
    causal_link_count: int,
) -> None:
    """Emit a harvest.complete audit event.

    Requirements: 52-REQ-4.1, 52-REQ-4.E1
    """
    if sink_dispatcher is None or not run_id:
        return
    try:
        from agent_fox.knowledge.audit import AuditEvent, AuditEventType

        categories = list({f.category for f in facts if hasattr(f, "category")})
        event = AuditEvent(
            run_id=run_id,
            event_type=AuditEventType.HARVEST_COMPLETE,
            node_id=node_id,
            payload={
                "fact_count": len(facts),
                "categories": categories,
                "causal_link_count": causal_link_count,
            },
        )
        sink_dispatcher.emit_audit_event(event)
    except Exception:
        logger.debug("Failed to emit harvest.complete audit event", exc_info=True)


def _emit_harvest_empty(
    sink_dispatcher: Any | None,
    run_id: str,
    node_id: str,
) -> None:
    """Emit a harvest.empty audit event (warning severity).

    Requirements: 52-REQ-4.2, 52-REQ-4.E1
    """
    if sink_dispatcher is None or not run_id:
        return
    try:
        from agent_fox.knowledge.audit import (
            AuditEvent,
            AuditEventType,
            AuditSeverity,
        )

        event = AuditEvent(
            run_id=run_id,
            event_type=AuditEventType.HARVEST_EMPTY,
            severity=AuditSeverity.WARNING,
            node_id=node_id,
            payload={},
        )
        sink_dispatcher.emit_audit_event(event)
    except Exception:
        logger.debug("Failed to emit harvest.empty audit event", exc_info=True)


def sync_facts_to_duckdb(
    knowledge_db: KnowledgeDB,
    facts: list[Any],
) -> None:
    """Insert facts into DuckDB memory_facts so causal links can reference them.

    Uses INSERT OR IGNORE for idempotency. Raises on DuckDB errors.

    Requirements: 38-REQ-2.1, 38-REQ-3.4
    """
    conn = knowledge_db.connection
    for fact in facts:
        conn.execute(
            "INSERT OR IGNORE INTO memory_facts "
            "(id, content, category, spec_name, session_id, "
            "commit_sha, confidence, created_at) "
            "VALUES (?::UUID, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [
                fact.id,
                fact.content,
                fact.category,
                fact.spec_name,
                getattr(fact, "session_id", None),
                getattr(fact, "commit_sha", None),
                fact.confidence,
            ],
        )


def _select_causal_context(
    knowledge_db: KnowledgeDB,
    prior_facts: list[Any],
    new_facts: list[Any],
    causal_context_limit: int,
) -> list[dict]:
    """Select prior facts for causal extraction, respecting the context limit.

    When the number of prior facts exceeds causal_context_limit, rank them
    by embedding similarity to the new facts and include only the top N.
    Facts lacking embeddings are appended after the ranked facts, up to
    the limit.

    Requirements: 52-REQ-6.1, 52-REQ-6.2, 52-REQ-6.E1
    """
    if len(prior_facts) <= causal_context_limit:
        return [{"id": f.id, "content": f.content} for f in prior_facts]

    conn = knowledge_db.connection

    # Collect embeddings for new facts from the DB
    new_embeddings: list[list[float]] = []
    for fact in new_facts:
        try:
            row = conn.execute(
                "SELECT embedding FROM memory_embeddings WHERE id = ?::UUID",
                [fact.id],
            ).fetchone()
            if row is not None:
                new_embeddings.append(list(row[0]))
        except Exception:
            logger.debug(
                "Could not load embedding for new fact %s",
                fact.id,
                exc_info=True,
            )

    if not new_embeddings:
        # No embeddings for new facts — fall back to first N prior facts
        logger.debug(
            "No new-fact embeddings available; using first %d prior facts in causal context",
            causal_context_limit,
        )
        return [{"id": f.id, "content": f.content} for f in prior_facts[:causal_context_limit]]

    # Average the new-fact embeddings
    dim = len(new_embeddings[0])
    avg_embedding = [sum(e[i] for e in new_embeddings) / len(new_embeddings) for i in range(dim)]

    # Rank prior facts with embeddings by similarity to the average embedding
    try:
        rows = conn.execute(
            f"""
            SELECT CAST(f.id AS VARCHAR) AS fact_id, f.content,
                   1 - array_cosine_distance(
                       e.embedding, ?::FLOAT[{dim}]
                   ) AS similarity
            FROM memory_embeddings e
            JOIN memory_facts f ON e.id = f.id
            WHERE f.superseded_by IS NULL
            ORDER BY similarity DESC
            LIMIT ?
            """,
            [avg_embedding, causal_context_limit],
        ).fetchall()
    except Exception:
        logger.warning(
            "Similarity ranking failed; using first %d prior facts",
            causal_context_limit,
            exc_info=True,
        )
        return [{"id": f.id, "content": f.content} for f in prior_facts[:causal_context_limit]]

    ranked_ids = {row[0] for row in rows}
    ranked_dicts = [{"id": row[0], "content": row[1]} for row in rows]

    # Append unembedded prior facts (not in ranked results) up to the limit
    remaining = causal_context_limit - len(ranked_dicts)
    if remaining > 0:
        unembedded_dicts = [{"id": f.id, "content": f.content} for f in prior_facts if f.id not in ranked_ids]
        ranked_dicts.extend(unembedded_dicts[:remaining])

    return ranked_dicts


def _extract_causal_links(
    new_facts: list[Any],
    node_id: str,
    memory_extraction_model: str,
    knowledge_db: KnowledgeDB,
    *,
    causal_context_limit: int = 200,
    sink_dispatcher: Any | None = None,
    run_id: str = "",
) -> int:
    """Extract and store causal links between new and prior facts.

    Loads prior facts (bounded by causal_context_limit via similarity
    ranking when needed), builds a causal extraction prompt, sends it to
    the LLM, parses causal links from the response, stores them in the
    DuckDB fact_causes table, and emits a fact.causal_links audit event.

    Returns the number of new causal links stored.

    Raises on DuckDB errors instead of silently continuing.

    Requirements: 13-REQ-2.1, 13-REQ-2.2, 13-REQ-3.1,
                  38-REQ-2.1, 38-REQ-3.3, 52-REQ-6.1, 52-REQ-6.2,
                  52-REQ-6.E1, 52-REQ-7.2
    """
    prior_facts = load_all_facts(knowledge_db.connection)

    # 52-REQ-6.1, 52-REQ-6.2, 52-REQ-6.E1: Apply context window bounding
    prior_dicts = _select_causal_context(knowledge_db, prior_facts, new_facts, causal_context_limit)
    # Include new facts so the LLM can link them
    all_dicts = list(prior_dicts)
    for f in new_facts:
        all_dicts.append({"id": f.id, "content": f.content})

    if len(all_dicts) < 2:
        return 0

    # Build the new-facts summary as the base prompt
    new_summary = "\n".join(f"- [{f.id}] {f.content}" for f in new_facts)

    # Enrich with causal extraction instructions
    prompt = enrich_extraction_with_causal(new_summary, all_dicts)

    # Call the LLM for causal analysis
    from agent_fox.core.client import (
        cached_messages_create_sync,
        create_anthropic_client,
    )
    from agent_fox.core.models import resolve_model
    from agent_fox.core.retry import retry_api_call

    model_entry = resolve_model(memory_extraction_model)
    client = create_anthropic_client()
    response = retry_api_call(
        lambda: cached_messages_create_sync(
            client,
            model=model_entry.model_id,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        ),
        context="causal link extraction",
    )

    track_response_usage(response, model_entry.model_id, "causal link extraction")

    raw_text = getattr(response.content[0], "text", "[]")
    links = parse_causal_links(raw_text)
    stored = 0
    if links:
        # Prior facts already exist in DuckDB (loaded via load_all_facts)
        # and new facts were inserted by the caller (sync_facts_to_duckdb),
        # so all referenced IDs are present for the referential integrity
        # check in store_causal_links.
        stored = store_causal_links(knowledge_db.connection, links)
        logger.info(
            "Stored %d causal links for session %s",
            stored,
            node_id,
        )

    # 52-REQ-7.2: Emit fact.causal_links audit event
    if sink_dispatcher is not None and run_id:
        try:
            from agent_fox.knowledge.audit import AuditEvent, AuditEventType

            row = knowledge_db.connection.execute("SELECT COUNT(*) FROM fact_causes").fetchone()
            total_link_count = row[0] if row else 0
            event = AuditEvent(
                run_id=run_id,
                event_type=AuditEventType.FACT_CAUSAL_LINKS,
                node_id=node_id,
                payload={
                    "new_link_count": stored,
                    "total_link_count": total_link_count,
                },
            )
            sink_dispatcher.emit_audit_event(event)
        except Exception:
            logger.debug("Failed to emit fact.causal_links audit event", exc_info=True)

    return stored
