"""Extract facts from session transcripts using an LLM.

Requirements: 05-REQ-1.1, 05-REQ-1.2, 05-REQ-1.3, 05-REQ-1.E1,
              05-REQ-1.E2, 05-REQ-2.2, 13-REQ-2.1, 13-REQ-2.2, 13-REQ-2.E1
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime

from anthropic.types import TextBlock

from agent_fox.core.client import create_async_anthropic_client
from agent_fox.core.models import resolve_model
from agent_fox.memory.types import Category, ConfidenceLevel, Fact

logger = logging.getLogger("agent_fox.memory.extraction")

_VALID_CATEGORIES = {c.value for c in Category}
_VALID_CONFIDENCE_LEVELS = {c.value for c in ConfidenceLevel}

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
    model_entry = resolve_model(model_name)
    prompt = EXTRACTION_PROMPT.format(transcript=transcript)

    client = create_async_anthropic_client()
    response = await client.messages.create(
        model=model_entry.model_id,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    first_block = response.content[0]
    if isinstance(first_block, TextBlock):
        raw_text: str = first_block.text
    else:
        # Fallback for types with a .text attribute (e.g. test mocks)
        maybe_text: str | None = getattr(first_block, "text", None)
        if maybe_text is None:
            logger.warning("Extraction response has no text content, skipping")
            return []
        raw_text = maybe_text

    try:
        facts = _parse_extraction_response(raw_text, spec_name, session_id)
    except ValueError:
        logger.warning("Extraction returned invalid JSON, skipping fact extraction")
        logger.debug("Raw extraction response was: %s", raw_text[:500])
        return []

    if not facts:
        logger.debug("Extraction returned zero facts for spec %s", spec_name)

    return facts


CAUSAL_EXTRACTION_ADDENDUM = """
## Causal Relationships

Review the facts you have extracted above. For each fact, consider whether
it was CAUSED BY a prior fact from the knowledge base, or whether it CAUSES
a change that affects other known facts.

For each causal relationship you identify, output a JSON object:
{{
    "cause_id": "<UUID of the cause fact>",
    "effect_id": "<UUID of the effect fact>"
}}

Only include relationships where the causal connection is clear and direct.
Do not speculate. If no causal relationships are apparent, output an empty
list.

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
        facts_text = "\n".join(
            f"- [{fact.get('id', 'unknown')}] {fact.get('content', '')}"
            for fact in prior_facts
        )
    else:
        facts_text = "(no prior facts available)"

    addendum = CAUSAL_EXTRACTION_ADDENDUM.format(prior_facts=facts_text)
    return base_prompt + addendum


def parse_causal_links(extraction_response: str) -> list[tuple[str, str]]:
    """Parse causal link pairs from the extraction model's response.

    Returns a list of (cause_id, effect_id) tuples. Silently skips
    malformed entries.
    """
    cleaned = _strip_markdown_fences(extraction_response)
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse causal links JSON, returning empty list")
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


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences and surrounding prose from LLM output.

    Handles ```json ... ```, ``` ... ```, and plain text wrapping a JSON
    array.  Returns the inner text if fences are found, otherwise attempts
    to locate a top-level JSON array bracket pair.
    """
    # 1. Strip ```json ... ``` or ``` ... ``` fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    # 2. If the raw text isn't already valid JSON, try to extract [...]
    stripped = text.strip()
    if stripped.startswith("["):
        return stripped

    # 3. Find a valid JSON array using bracket-depth counting.
    # The greedy regex (\[.*\]) fails when prose contains [bracketed]
    # references (e.g. [uuid]) before the actual JSON array.
    for match in re.finditer(r"\[", stripped):
        start = match.start()
        depth = 0
        for i, ch in enumerate(stripped[start:], start=start):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    candidate = stripped[start : i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except (json.JSONDecodeError, ValueError):
                        break

    # 4. Give up — return original text so json.loads produces a clear error
    return stripped


def _parse_extraction_response(
    raw_response: str,
    spec_name: str,
    session_id: str | None = None,
) -> list[Fact]:
    """Parse LLM JSON response into Fact objects.

    Validates categories and confidence levels, assigning defaults for
    invalid values. Generates UUIDs and timestamps for each fact.

    Args:
        raw_response: The raw JSON string from the LLM.
        spec_name: The specification name for provenance.

    Returns:
        A list of validated Fact objects.

    Raises:
        ValueError: If the response is not valid JSON.
    """
    cleaned = _strip_markdown_fences(raw_response)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in extraction response: {exc}") from exc

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

        # Validate category -- default to gotcha for unknown values
        category = item.get("category", "gotcha")
        if category not in _VALID_CATEGORIES:
            logger.warning("Unknown category '%s', defaulting to 'gotcha'", category)
            category = Category.GOTCHA.value

        # Validate confidence -- default to medium for unknown values
        confidence = item.get("confidence", "medium")
        if confidence not in _VALID_CONFIDENCE_LEVELS:
            logger.warning(
                "Unknown confidence '%s', defaulting to 'medium'", confidence
            )
            confidence = ConfidenceLevel.MEDIUM.value

        keywords = item.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []

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
