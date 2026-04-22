"""Gotcha extraction from session transcripts via LLM.

Extracts 0-3 surprising or non-obvious findings from session context
by prompting an LLM. The extracted candidates are stored by the gotcha
store module.

Requirements: 115-REQ-2.1, 115-REQ-2.2, 115-REQ-2.3, 115-REQ-2.E2, 115-REQ-2.E3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GotchaCandidate:
    """A single gotcha candidate extracted from a session transcript.

    Attributes:
        text: The gotcha description text.
        content_hash: SHA-256 of normalized text, computed at extraction time.
    """

    text: str
    content_hash: str


def _call_llm(context: dict, model_tier: str) -> list[GotchaCandidate]:
    """Call the LLM to extract gotcha candidates from session context.

    This is an internal function that will be implemented in task group 4.
    Tests can patch this function to inject mock LLM responses.
    """
    raise NotImplementedError("LLM gotcha extraction not yet implemented")


def extract_gotchas(
    context: dict,
    model_tier: str = "SIMPLE",
) -> list[GotchaCandidate]:
    """Prompt the LLM for 0-3 gotcha candidates.

    Caps at 3 even if LLM returns more. Returns empty list on LLM failure.

    Args:
        context: Session context dict with session_status, touched_files, etc.
        model_tier: LLM model tier to use (default SIMPLE).

    Returns:
        List of 0-3 GotchaCandidate objects.
    """
    raise NotImplementedError("Gotcha extraction not yet implemented")
