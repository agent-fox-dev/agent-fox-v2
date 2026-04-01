"""JSON array extraction from LLM output text.

Provides a single robust function to extract a JSON array from text
that may contain prose, markdown code fences, or bare arrays. Uses
``json.JSONDecoder.raw_decode()`` for correct handling of brackets
inside JSON strings.

Consolidates the extraction logic previously duplicated in
``engine.review_parser`` and ``knowledge.extraction``.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# Regex for markdown code fences (```json ... ``` or ``` ... ```)
_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)


def extract_json_array(
    output_text: str,
    *,
    repair_truncated: bool = False,
) -> list[dict] | None:
    """Extract a JSON array from LLM output text.

    Strategy 1: Scan left-to-right for bracket-delimited arrays using
    ``json.JSONDecoder.raw_decode()``; return the first valid JSON list.

    Strategy 2: If no valid bare array found, scan markdown code fences
    (``\u0060\u0060\u0060json ... \u0060\u0060\u0060``) for a valid JSON list.

    Strategy 3 (opt-in): If *repair_truncated* is True and strategies 1-2
    fail, attempt to recover partial results from a truncated JSON array
    (e.g. ``[{"a":1},{"b":2},{"c"``).

    Returns None if no valid JSON array is found anywhere in the text.
    """
    if not output_text:
        return None

    # Strategy 1: bracket-scan from left to right
    result = _scan_bracket_arrays(output_text)
    if result is not None:
        return result

    # Strategy 2: markdown fences
    for match in _FENCE_RE.finditer(output_text):
        content = match.group(1).strip()
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return parsed  # type: ignore[return-value]
        except (json.JSONDecodeError, ValueError):
            continue

    # Strategy 3: truncation repair (opt-in)
    if repair_truncated:
        return _repair_truncated_json_array(output_text)

    return None


def _scan_bracket_arrays(text: str) -> list[dict] | None:
    """Scan text left-to-right for bracket-delimited JSON arrays.

    Uses ``json.JSONDecoder.raw_decode()`` to properly handle brackets
    inside JSON strings, nested objects, and other edge cases.
    """
    decoder = json.JSONDecoder()
    pos = 0
    text_len = len(text)

    while pos < text_len:
        start = text.find("[", pos)
        if start == -1:
            break

        try:
            parsed, _ = decoder.raw_decode(text, start)
            if isinstance(parsed, list):
                return parsed  # type: ignore[return-value]
        except (json.JSONDecodeError, ValueError):
            pass

        pos = start + 1

    return None


def _repair_truncated_json_array(text: str) -> list[dict] | None:
    """Try to recover valid entries from a truncated JSON array.

    When an LLM response is cut off mid-stream, the JSON may be
    incomplete (e.g. ``[{"a":1},{"b":2},{"c"``). Finds the last
    complete object and returns all complete objects parsed so far.
    """
    # Find the start of the array
    stripped = text.strip()
    idx = stripped.find("[")
    if idx == -1:
        return None

    array_text = stripped[idx:]

    last_complete = array_text.rfind("},")
    if last_complete == -1:
        last_complete = array_text.rfind("}")
    if last_complete == -1:
        return None

    candidate = array_text[: last_complete + 1] + "]"
    try:
        data = json.loads(candidate)
        if isinstance(data, list) and len(data) > 0:
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None
