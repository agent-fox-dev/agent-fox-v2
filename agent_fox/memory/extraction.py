"""Extract facts from session transcripts using an LLM.

Requirements: 05-REQ-1.1, 05-REQ-1.2, 05-REQ-1.3, 05-REQ-1.E1,
              05-REQ-1.E2, 05-REQ-2.2
"""

from __future__ import annotations

import logging

import anthropic  # noqa: F401

from agent_fox.memory.types import Fact

logger = logging.getLogger("agent_fox.memory.extraction")

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
    raise NotImplementedError


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
    raise NotImplementedError
