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
    ``json.JSONDecoder.raw_decode()``; prefer arrays where at least one item
    is a dict over primitive-only arrays (e.g. string arrays in prose).

    Strategy 2: If no valid bare array found, scan markdown code fences
    (``\u0060\u0060\u0060json ... \u0060\u0060\u0060``) for a valid JSON list.
    Single-key wrapper objects like ``{"findings": [...]}`` are unwrapped
    automatically (Option A).

    Strategy 3 (opt-in): If *repair_truncated* is True and strategies 1-2
    fail, attempt to recover partial results from a truncated JSON array
    (e.g. ``[{"a":1},{"b":2},{"c"``).

    Returns None if no valid JSON array is found anywhere in the text.
    """
    if not output_text:
        return None

    # Strategy 1: bracket-scan from left to right (two-pass: prefer dict arrays)
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
            # Option A: unwrap single-key wrapper objects like {"findings": [...]}
            unwrapped = _unwrap_single_key_list(parsed)
            if unwrapped is not None:
                return unwrapped  # type: ignore[return-value]
        except (json.JSONDecodeError, ValueError):
            continue

    # Strategy 3: truncation repair (opt-in)
    if repair_truncated:
        return _repair_truncated_json_array(output_text)

    return None


def extract_json_object(text: str) -> dict:
    """Extract a JSON object (dict) from LLM output text.

    Strategy 1: Try direct ``json.loads()`` on the stripped text.

    Strategy 2: Strip markdown code fences and retry.

    Strategy 3: Use ``json.JSONDecoder.raw_decode()`` to find the
    first JSON object in the text.

    Raises ``ValueError`` if no valid JSON object is found.
    """
    stripped = text.strip()

    # Strategy 1: direct parse
    try:
        result = json.loads(stripped)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Strategy 2: markdown fence stripping
    for match in _FENCE_RE.finditer(stripped):
        content = match.group(1).strip()
        try:
            result = json.loads(content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    # Strategy 3: raw_decode scan for first object
    try:
        obj, _ = json.JSONDecoder().raw_decode(stripped)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    raise ValueError("No JSON object found in text")


def _unwrap_single_key_list(obj: object) -> list | None:
    """Unwrap a single-key dict whose value is a list.

    Handles the common LLM pattern of wrapping array output in a named
    object, e.g. ``{"findings": [...]}``.  Returns ``None`` if *obj* is
    not a single-key dict or its value is not a list.
    """
    if isinstance(obj, dict) and len(obj) == 1:
        value = next(iter(obj.values()))
        if isinstance(value, list):
            return value
    return None


_DECODER = json.JSONDecoder()


def _scan_bracket_arrays(text: str) -> list[dict] | None:
    """Scan text left-to-right for bracket-delimited JSON arrays.

    Uses ``json.JSONDecoder.raw_decode()`` to properly handle brackets
    inside JSON strings, nested objects, and other edge cases.

    Two-pass strategy (Option B):

    - **First pass:** accept only arrays where at least one item is a dict.
    - **Second pass (fallback):** accept any valid array.

    This ensures prose string arrays (e.g. ``["req-1", "req-2"]``) are
    skipped when a real findings array of objects exists later in the text.
    """
    decoder = _DECODER
    pos = 0
    text_len = len(text)
    first_primitive_array: list | None = None  # fallback when no dict array found

    while pos < text_len:
        start = text.find("[", pos)
        if start == -1:
            break

        try:
            parsed, _ = decoder.raw_decode(text, start)
            if isinstance(parsed, list):
                # Prefer arrays containing at least one dict item (Option B).
                if any(isinstance(item, dict) for item in parsed):
                    return parsed  # type: ignore[return-value]
                # Remember first primitive array as a fallback.
                if first_primitive_array is None:
                    first_primitive_array = parsed
        except (json.JSONDecodeError, ValueError):
            pass

        pos = start + 1

    return first_primitive_array


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
