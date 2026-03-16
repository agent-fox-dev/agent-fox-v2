"""Knowledge harvesting: extract facts and causal links from sessions.

Separated from session_lifecycle.py to isolate the LLM-powered knowledge
extraction concern from the session lifecycle orchestration.

Requirements: 05-REQ-1.1, 05-REQ-1.E1, 13-REQ-2.1, 13-REQ-2.2, 13-REQ-3.1,
              40-REQ-11.4
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agent_fox.core.token_tracker import record_auxiliary_usage
from agent_fox.knowledge.causal import store_causal_links
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.extraction import (
    enrich_extraction_with_causal,
    extract_facts,
    parse_causal_links,
)
from agent_fox.knowledge.store import load_all_facts

if TYPE_CHECKING:
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
) -> None:
    """Extract facts and causal links from a session transcript.

    1. Calls the LLM to extract facts from the transcript.
    2. Writes facts to DuckDB via sync_facts_to_duckdb.
    3. Extracts and stores causal links in DuckDB.

    Requirements: 05-REQ-1.1, 05-REQ-1.E1, 13-REQ-2.1, 13-REQ-2.2,
                  38-REQ-2.1, 38-REQ-2.3, 39-REQ-3.1
    """
    facts = await extract_facts(
        transcript, spec_name, memory_extraction_model, session_id=node_id
    )
    if facts:
        sync_facts_to_duckdb(knowledge_db, facts)
        logger.info(
            "Extracted %d facts from session %s",
            len(facts),
            node_id,
        )
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

        _extract_causal_links(facts, node_id, memory_extraction_model, knowledge_db)


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


def _extract_causal_links(
    new_facts: list[Any],
    node_id: str,
    memory_extraction_model: str,
    knowledge_db: KnowledgeDB,
) -> None:
    """Extract and store causal links between new and prior facts.

    Loads prior facts, builds a causal extraction prompt, sends
    it to the LLM, parses causal links from the response, and
    stores them in the DuckDB fact_causes table.

    Raises on DuckDB errors instead of silently continuing.

    Requirements: 13-REQ-2.1, 13-REQ-2.2, 13-REQ-3.1,
                  38-REQ-2.1, 38-REQ-3.3
    """
    prior_facts = load_all_facts(knowledge_db.connection)
    all_dicts = [{"id": f.id, "content": f.content} for f in prior_facts]
    # Include new facts so the LLM can link them
    for f in new_facts:
        all_dicts.append({"id": f.id, "content": f.content})

    if len(all_dicts) < 2:
        return

    # Build the new-facts summary as the base prompt
    new_summary = "\n".join(f"- [{f.id}] {f.content}" for f in new_facts)

    # Enrich with causal extraction instructions
    prompt = enrich_extraction_with_causal(new_summary, all_dicts)

    # Call the LLM for causal analysis
    from agent_fox.core.client import create_anthropic_client
    from agent_fox.core.models import resolve_model
    from agent_fox.core.retry import retry_api_call

    model_entry = resolve_model(memory_extraction_model)
    client = create_anthropic_client()
    response = retry_api_call(
        lambda: client.messages.create(
            model=model_entry.model_id,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        ),
        context="causal link extraction",
    )

    # Track auxiliary token usage (34-REQ-1.5)
    usage = getattr(response, "usage", None)
    if usage is not None:
        record_auxiliary_usage(
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            model=model_entry.model_id,
        )
    else:
        logger.warning("API response for causal link extraction lacks usage data")
        record_auxiliary_usage(0, 0, model_entry.model_id)

    raw_text = getattr(response.content[0], "text", "[]")
    links = parse_causal_links(raw_text)
    if links:
        # Sync ALL facts (prior + new) to DuckDB so the
        # referential integrity check in store_causal_links
        # can find every fact the LLM may have referenced.
        all_facts = list(prior_facts) + list(new_facts)
        sync_facts_to_duckdb(knowledge_db, all_facts)
        stored = store_causal_links(knowledge_db.connection, links)
        logger.info(
            "Stored %d causal links for session %s",
            stored,
            node_id,
        )
