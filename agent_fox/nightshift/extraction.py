"""Knowledge extraction from session transcripts.

This module provides the extraction interface for future implementation.
The ``extract_knowledge`` function is currently a stub that returns an empty
result. A future spec will implement LLM-driven fact extraction.

Requirements: 100-REQ-4.1, 100-REQ-4.2, 100-REQ-4.3, 100-REQ-4.E1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractionInput:
    """Input for knowledge extraction from a session transcript.

    Requirements: 100-REQ-4.1
    """

    session_id: str
    transcript: str
    spec_name: str
    archetype: str
    mode: str | None = None


@dataclass(frozen=True)
class ExtractionResult:
    """Result of knowledge extraction.

    Requirements: 100-REQ-4.2
    """

    facts: list[dict] = field(default_factory=list)
    session_id: str = ""
    status: str = "not_implemented"


def extract_knowledge(extraction_input: ExtractionInput) -> ExtractionResult:
    """Extract knowledge from a session transcript.

    Currently returns an empty result with status='not_implemented'. Will be
    implemented in a future spec to use LLM-driven fact extraction.

    This function never raises an exception (100-REQ-4.E1).

    Requirements: 100-REQ-4.3, 100-REQ-4.E1

    Args:
        extraction_input: The session transcript and metadata to extract from.

    Returns:
        An ``ExtractionResult`` with ``status="not_implemented"`` and an empty
        ``facts`` list. The ``session_id`` is propagated from the input.
    """
    logger.info(
        "Knowledge extraction not yet implemented for session %s",
        extraction_input.session_id,
    )
    return ExtractionResult(
        session_id=extraction_input.session_id,
        status="not_implemented",
    )
