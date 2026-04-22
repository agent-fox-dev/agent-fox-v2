"""Gotcha extraction from session transcripts via LLM.

Extracts 0-3 surprising or non-obvious findings from session context
by prompting an LLM. The extracted candidates are stored by the gotcha
store module.

Requirements: 115-REQ-2.1, 115-REQ-2.2, 115-REQ-2.3, 115-REQ-2.E2, 115-REQ-2.E3
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_MAX_GOTCHAS = 3

_EXTRACTION_PROMPT = """\
Based on this coding session, what was surprising or non-obvious?
What would you want to know if you were starting a new session on this spec?

Return 0-3 bullet points. Each should describe ONE specific gotcha:
something that looks like it should work but doesn't, a hidden constraint,
or an unexpected behavior. Return nothing if the session was straightforward.

Session context:
- Spec: {spec_name}
- Touched files: {touched_files}
- Status: {session_status}"""

# Matches bullet point markers: -, *, bullet char, or numbered (1. / 1))
_BULLET_RE = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)]\s)")


@dataclass(frozen=True)
class GotchaCandidate:
    """A single gotcha candidate extracted from a session transcript.

    Attributes:
        text: The gotcha description text.
        content_hash: SHA-256 of normalized text, computed at extraction time.
    """

    text: str
    content_hash: str


def _parse_bullets(text: str) -> list[str]:
    """Parse bullet points from LLM response text.

    Lines beginning with ``-``, ``*``, or a digit followed by ``.`` or ``)``
    are treated as bullet starts.  Continuation lines (non-bullet, non-blank)
    are appended to the current bullet.

    Returns:
        List of extracted bullet-point texts (stripped of markers).
    """
    lines = text.strip().split("\n")
    bullets: list[str] = []
    current: str | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # Blank line ends current bullet
            if current is not None:
                bullets.append(current.strip())
                current = None
            continue

        if _BULLET_RE.match(stripped):
            # New bullet — flush previous
            if current is not None:
                bullets.append(current.strip())
            # Remove the bullet marker
            current = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)]\s*)\s*", "", stripped)
        elif current is not None:
            # Continuation of previous bullet
            current += " " + stripped
        # else: preamble text before first bullet — ignore

    # Flush last bullet
    if current is not None:
        bullets.append(current.strip())

    return [b for b in bullets if b]


def _call_llm(context: dict, model_tier: str) -> list[GotchaCandidate]:
    """Call the LLM to extract gotcha candidates from session context.

    This is an internal function.  Tests can patch this function to inject
    mock LLM responses without hitting the real API.

    Args:
        context: Session context dict with spec_name, touched_files, etc.
        model_tier: LLM model tier to use (e.g. "SIMPLE").

    Returns:
        List of GotchaCandidate objects (may exceed _MAX_GOTCHAS — the
        caller is responsible for capping).
    """
    from agent_fox.core.client import ai_call_sync
    from agent_fox.knowledge.gotcha_store import compute_content_hash

    spec_name = context.get("spec_name", "unknown")
    touched_files = context.get("touched_files", [])
    session_status = context.get("session_status", "unknown")

    prompt = _EXTRACTION_PROMPT.format(
        spec_name=spec_name,
        touched_files=", ".join(str(f) for f in touched_files) if touched_files else "none",
        session_status=session_status,
    )

    output_text, _response = ai_call_sync(
        model_tier=model_tier,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        context="gotcha extraction",
    )

    if output_text is None:
        return []

    bullets = _parse_bullets(output_text)
    candidates: list[GotchaCandidate] = []
    for text in bullets:
        content_hash = compute_content_hash(text)
        candidates.append(GotchaCandidate(text=text, content_hash=content_hash))

    return candidates


def extract_gotchas(
    context: dict,
    model_tier: str = "SIMPLE",
) -> list[GotchaCandidate]:
    """Prompt the LLM for 0-3 gotcha candidates.

    Caps at 3 even if LLM returns more.  Returns empty list on LLM failure.

    Args:
        context: Session context dict with session_status, touched_files, etc.
        model_tier: LLM model tier to use (default SIMPLE).

    Returns:
        List of 0-3 GotchaCandidate objects.
    """
    try:
        candidates = _call_llm(context, model_tier)
    except Exception:
        logger.warning("Gotcha extraction failed", exc_info=True)
        return []

    return candidates[:_MAX_GOTCHAS]
