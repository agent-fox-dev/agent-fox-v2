"""LLM-powered contradiction classification for fact pairs.

Requirements: 90-REQ-2.2, 90-REQ-2.5, 90-REQ-2.E1, 90-REQ-2.E3
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent_fox.knowledge.lifecycle import ContradictionVerdict

if TYPE_CHECKING:
    from agent_fox.knowledge.facts import Fact

logger = logging.getLogger("agent_fox.knowledge.contradiction")

CONTRADICTION_PROMPT = """You are a knowledge base curator. For each pair of facts below, determine
whether the NEW fact contradicts the OLD fact. A contradiction means the
new fact makes the old fact incorrect, outdated, or misleading.

Respond with ONLY a JSON array. For each pair, return:
{{"pair_index": <N>, "contradicts": true/false, "reason": "..."}}

Pairs:
{pairs}"""


def classify_contradiction_batch(
    pairs: list[tuple[Fact, Fact]],
    model: str = "SIMPLE",
) -> list[ContradictionVerdict]:
    """Classify a batch of fact pairs for contradiction via LLM.

    Each pair is (new_fact, old_fact). Calls the LLM with the batch using
    CONTRADICTION_PROMPT and parses the JSON response into ContradictionVerdict
    objects.

    On API error or malformed JSON, logs a warning and returns an empty list
    so the caller can continue without blocking ingestion (90-REQ-2.E1,
    90-REQ-2.E3).

    Requirements: 90-REQ-2.2, 90-REQ-2.5
    """
    if not pairs:
        return []

    # Build pairs text for the prompt
    pairs_lines = []
    for i, (new_fact, old_fact) in enumerate(pairs, start=1):
        old_content = old_fact.content.replace('"', '\\"')
        new_content = new_fact.content.replace('"', '\\"')
        pairs_lines.append(f'{i}. OLD: "{old_content}"   NEW: "{new_content}"')

    pairs_text = "\n".join(pairs_lines)
    prompt = CONTRADICTION_PROMPT.format(pairs=pairs_text)

    from agent_fox.core.client import cached_messages_create_sync, create_anthropic_client
    from agent_fox.core.json_extraction import extract_json_array
    from agent_fox.core.models import resolve_model
    from agent_fox.core.retry import retry_api_call

    model_entry = resolve_model(model)
    client = create_anthropic_client()

    def _call():
        return cached_messages_create_sync(
            client,
            model=model_entry.model_id,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

    try:
        response = retry_api_call(_call, context="contradiction classification")
    except Exception:
        logger.warning(
            "Contradiction LLM call failed for batch of %d pair(s)",
            len(pairs),
            exc_info=True,
        )
        return []

    # Extract text from response
    output_text = ""
    if response.content:
        output_text = response.content[0].text

    # Parse JSON array from response (90-REQ-2.E3: malformed → non-contradiction)
    items = extract_json_array(output_text)
    if items is None:
        logger.warning(
            "Contradiction LLM returned non-parseable JSON for batch of %d pair(s): %r",
            len(pairs),
            output_text[:200],
        )
        return []

    verdicts: list[ContradictionVerdict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "contradicts" not in item:
            # Missing required field → treat as non-contradiction (90-REQ-2.E3)
            continue

        pair_index = item.get("pair_index")
        if not isinstance(pair_index, int) or not (1 <= pair_index <= len(pairs)):
            logger.warning("Contradiction LLM returned invalid pair_index: %r", pair_index)
            continue

        new_fact, old_fact = pairs[pair_index - 1]
        verdicts.append(
            ContradictionVerdict(
                new_fact_id=new_fact.id,
                old_fact_id=old_fact.id,
                contradicts=bool(item.get("contradicts", False)),
                reason=str(item.get("reason", "")),
            )
        )

    return verdicts
