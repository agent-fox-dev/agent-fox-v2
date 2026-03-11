"""Knowledge harvesting: extract facts and causal links from sessions.

Separated from session_lifecycle.py to isolate the LLM-powered knowledge
extraction concern from the session lifecycle orchestration.

Requirements: 05-REQ-1.1, 05-REQ-1.E1, 13-REQ-2.1, 13-REQ-2.2, 13-REQ-3.1
"""

from __future__ import annotations

import logging
from typing import Any

from agent_fox.core.token_tracker import record_auxiliary_usage
from agent_fox.knowledge.causal import store_causal_links
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.memory.extraction import (
    enrich_extraction_with_causal,
    extract_facts,
    parse_causal_links,
)
from agent_fox.memory.memory import append_facts, load_all_facts

logger = logging.getLogger(__name__)


async def extract_and_store_knowledge(
    transcript: str,
    spec_name: str,
    node_id: str,
    memory_extraction_model: str,
    knowledge_db: KnowledgeDB | None = None,
) -> None:
    """Extract facts and causal links from a session transcript.

    1. Calls the LLM to extract facts from the transcript.
    2. Appends facts to the JSONL store.
    3. If DuckDB is available, extracts and stores causal links.

    Best-effort — all failures are logged and silently ignored.

    Requirements: 05-REQ-1.1, 05-REQ-1.E1, 13-REQ-2.1, 13-REQ-2.2
    """
    try:
        facts = await extract_facts(
            transcript, spec_name, memory_extraction_model, session_id=node_id
        )
        if facts:
            append_facts(facts)
            logger.info(
                "Extracted %d facts from session %s",
                len(facts),
                node_id,
            )
            _extract_causal_links(facts, node_id, memory_extraction_model, knowledge_db)
    except Exception:
        logger.warning(
            "Fact extraction failed for %s, continuing",
            node_id,
            exc_info=True,
        )


def sync_facts_to_duckdb(
    knowledge_db: KnowledgeDB | None,
    facts: list[Any],
) -> None:
    """Insert facts into DuckDB memory_facts so causal links can reference them.

    Best-effort: failures are logged and silently ignored.
    Uses INSERT OR IGNORE for idempotency.
    """
    if knowledge_db is None:
        return
    conn = knowledge_db.connection
    for fact in facts:
        try:
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
        except Exception:
            logger.debug(
                "Failed to sync fact %s to DuckDB",
                fact.id,
                exc_info=True,
            )


def _extract_causal_links(
    new_facts: list[Any],
    node_id: str,
    memory_extraction_model: str,
    knowledge_db: KnowledgeDB | None,
) -> None:
    """Extract and store causal links between new and prior facts.

    Loads prior facts, builds a causal extraction prompt, sends
    it to the LLM, parses causal links from the response, and
    stores them in the DuckDB fact_causes table.

    Best-effort — failures are logged only.

    Requirements: 13-REQ-2.1, 13-REQ-2.2, 13-REQ-3.1
    """
    if knowledge_db is None:
        return

    try:
        prior_facts = load_all_facts()
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

        model_entry = resolve_model(memory_extraction_model)
        client = create_anthropic_client()
        response = client.messages.create(
            model=model_entry.model_id,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
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
    except Exception:
        logger.debug(
            "Causal link extraction failed for %s, continuing",
            node_id,
            exc_info=True,
        )
