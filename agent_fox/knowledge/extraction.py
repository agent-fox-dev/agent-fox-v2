"""Extract facts from session transcripts using an LLM.

Requirements: 05-REQ-1.1, 05-REQ-1.2, 05-REQ-1.3, 05-REQ-1.E1,
              05-REQ-1.E2, 05-REQ-2.2, 13-REQ-2.1, 13-REQ-2.2, 13-REQ-2.E1
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from agent_fox.core.client import ai_call
from agent_fox.core.json_extraction import extract_json_array
from agent_fox.core.llm_validation import (
    MAX_CONTENT_LENGTH,
    check_response_size,
    truncate_field,
    validate_keywords,
)
from agent_fox.core.logging import TRACE
from agent_fox.core.prompt_safety import sanitize_prompt_content
from agent_fox.knowledge.facts import Category, Fact, parse_confidence

logger = logging.getLogger("agent_fox.knowledge.extraction")

_VALID_CATEGORIES = {c.value for c in Category}

EXTRACTION_PROMPT = """Analyze the following coding session transcript and extract
structured learnings. For each learning, provide:

- content: A clear, concise description of the learning (1-2 sentences).
- category: One of: gotcha, pattern, decision, convention, anti_pattern, fragile_area.
- confidence: One of: high, medium, low.
- keywords: A list of 2-5 relevant terms for matching this fact to future tasks.

Respond with a JSON array of objects. Example:
[
  {{
    "content": "The pytest-asyncio plugin requires mode='auto' in pyproject.toml.",
    "category": "gotcha",
    "confidence": "high",
    "keywords": ["pytest", "asyncio", "configuration"]
  }}
]

If no learnings are worth extracting, respond with an empty array: []

Session transcript:
{transcript}
"""


async def extract_facts(
    transcript: str,
    spec_name: str,
    model_name: str = "SIMPLE",
    session_id: str | None = None,
) -> list[Fact]:
    """Extract structured facts from a session transcript using an LLM.

    Args:
        transcript: The full session transcript text.
        spec_name: The specification name for provenance.
        model_name: The model tier or ID to use (default: SIMPLE).
        session_id: The node_id of the session that produced these facts.

    Returns:
        A list of Fact objects extracted from the transcript.
        Returns an empty list if extraction fails or yields no facts.
    """
    safe_transcript = sanitize_prompt_content(transcript, label="transcript", max_chars=100_000)
    prompt = EXTRACTION_PROMPT.format(transcript=safe_transcript)

    raw_text, _response = await ai_call(
        model_tier=model_name,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        context="fact extraction",
    )

    if raw_text is None:
        logger.warning("Extraction response has no text content, skipping")
        return []

    try:
        facts = _parse_extraction_response(raw_text, spec_name, session_id)
    except ValueError:
        logger.warning("Extraction returned invalid JSON, skipping fact extraction")
        logger.log(TRACE, "Raw extraction response was: %s", raw_text[:500])
        return []

    if not facts:
        logger.debug("Extraction returned zero facts for spec %s", spec_name)

    return facts


CAUSAL_EXTRACTION_ADDENDUM = """
## Causal Relationships

Review the facts you have extracted above. For each fact, consider whether
it was CAUSED BY a prior fact from the knowledge base, or whether it CAUSES
a change that affects other known facts.

Respond with ONLY a JSON array of causal link objects. Example:
[
  {{
    "cause_id": "<UUID of the cause fact>",
    "effect_id": "<UUID of the effect fact>"
  }}
]

If no causal relationships are apparent, respond with exactly: []

Only include relationships where the causal connection is clear and direct.
Do not speculate. Do not include any prose or explanation — only the JSON array.

Prior facts for reference:
{prior_facts}
"""


def enrich_extraction_with_causal(
    base_prompt: str,
    prior_facts: list[dict],
) -> str:
    """Append causal extraction instructions to the base extraction prompt.

    Formats the prior facts as a reference list and appends the causal
    extraction addendum to the prompt.
    """
    if prior_facts:
        facts_text = "\n".join(f"- [{fact.get('id', 'unknown')}] {fact.get('content', '')}" for fact in prior_facts)
    else:
        facts_text = "(no prior facts available)"

    safe_facts = sanitize_prompt_content(facts_text, label="prior-facts", max_chars=50_000)
    addendum = CAUSAL_EXTRACTION_ADDENDUM.format(prior_facts=safe_facts)
    return base_prompt + addendum


def parse_causal_links(extraction_response: str) -> list[tuple[str, str]]:
    """Parse causal link pairs from the extraction model's response.

    Returns a list of (cause_id, effect_id) tuples. Silently skips
    malformed entries.
    """
    data = extract_json_array(extraction_response, repair_truncated=True)
    if data is None:
        logger.warning(
            "Failed to parse causal links JSON, returning empty list. Response (first 300 chars): %s",
            extraction_response[:300],
        )
        return []

    if not isinstance(data, list):
        logger.warning("Causal links response is not a JSON array")
        return []

    links: list[tuple[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        cause_id = item.get("cause_id")
        effect_id = item.get("effect_id")
        if isinstance(cause_id, str) and isinstance(effect_id, str):
            links.append((cause_id, effect_id))
        else:
            logger.debug("Skipping malformed causal link entry: %s", item)
    return links


def _parse_extraction_response(
    raw_response: str,
    spec_name: str,
    session_id: str | None = None,
) -> list[Fact]:
    """Parse LLM JSON response into Fact objects.

    Validates categories and confidence levels, assigning defaults for
    invalid values. Enforces field-level length constraints to prevent
    memory exhaustion and prompt injection persistence (issue #186).
    Generates UUIDs and timestamps for each fact.

    Args:
        raw_response: The raw JSON string from the LLM.
        spec_name: The specification name for provenance.

    Returns:
        A list of validated Fact objects.

    Raises:
        ValueError: If the response is not valid JSON.
        ResponseTooLargeError: If the raw response exceeds the size limit.
    """
    check_response_size(raw_response, context="fact extraction response")
    data = extract_json_array(raw_response)
    if data is None:
        raise ValueError("Invalid JSON in extraction response: no JSON array found")

    if not isinstance(data, list):
        raise ValueError("Extraction response is not a JSON array")

    now = datetime.now(UTC).isoformat()
    facts: list[Fact] = []

    for item in data:
        if not isinstance(item, dict):
            continue

        content = item.get("content", "")
        if not content:
            continue

        # Field-level validation (issue #186)
        content = truncate_field(content, max_length=MAX_CONTENT_LENGTH, field_name="fact.content")

        # Validate category -- default to gotcha for unknown values
        category = item.get("category", "gotcha")
        if category not in _VALID_CATEGORIES:
            logger.warning("Unknown category '%s', defaulting to 'gotcha'", category)
            category = Category.GOTCHA.value

        # Convert confidence to float [0.0, 1.0] (37-REQ-1.1, 37-REQ-1.2)
        raw_confidence = item.get("confidence", None)
        confidence = parse_confidence(raw_confidence)

        keywords = item.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        keywords = validate_keywords(keywords)

        fact = Fact(
            id=str(uuid.uuid4()),
            content=content,
            category=category,
            spec_name=spec_name,
            keywords=keywords,
            confidence=confidence,
            created_at=now,
            supersedes=None,
            session_id=session_id,
        )
        facts.append(fact)

    return facts
