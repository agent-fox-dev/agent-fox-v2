"""Extract facts from session transcripts using an LLM.

Requirements: 05-REQ-1.1, 05-REQ-1.2, 05-REQ-1.3, 05-REQ-1.E1,
              05-REQ-1.E2, 05-REQ-2.2
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

import anthropic  # noqa: F401
from anthropic.types import TextBlock

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
) -> list[Fact]:
    """Extract structured facts from a session transcript using an LLM.

    Args:
        transcript: The full session transcript text.
        spec_name: The specification name for provenance.
        model_name: The model tier or ID to use (default: SIMPLE).

    Returns:
        A list of Fact objects extracted from the transcript.
        Returns an empty list if extraction fails or yields no facts.
    """
    model_entry = resolve_model(model_name)
    prompt = EXTRACTION_PROMPT.format(transcript=transcript)

    client = anthropic.AsyncAnthropic()
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
        facts = _parse_extraction_response(raw_text, spec_name)
    except ValueError:
        logger.warning(
            "Extraction returned invalid JSON, skipping fact extraction"
        )
        return []

    if not facts:
        logger.debug("Extraction returned zero facts for spec %s", spec_name)

    return facts


def _parse_extraction_response(
    raw_response: str,
    spec_name: str,
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
    try:
        data = json.loads(raw_response)
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
            logger.warning(
                "Unknown category '%s', defaulting to 'gotcha'", category
            )
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
        )
        facts.append(fact)

    return facts
