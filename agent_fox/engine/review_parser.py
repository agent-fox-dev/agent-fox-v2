"""JSON extraction and typed parsing for review archetype output.

Provides `extract_json_array()` to extract a JSON array from LLM output text
(handling prose, markdown fences, and bare arrays), and typed parse functions
that convert raw dicts into ReviewFinding, VerificationResult, and DriftFinding
dataclass instances.

Requirements: 53-REQ-4.1, 53-REQ-4.2, 53-REQ-4.E1
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from agent_fox.knowledge.review_store import (
    VALID_VERDICTS,
    DriftFinding,
    ReviewFinding,
    VerificationResult,
)

logger = logging.getLogger(__name__)

# Regex for markdown code fences (```json ... ``` or ``` ... ```)
_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)


def extract_json_array(output_text: str) -> list[dict] | None:
    """Extract a JSON array from archetype output text.

    Strategy 1: Scan left-to-right for bracket-delimited arrays using
    depth-tracking; return the first one that parses as a valid JSON list.

    Strategy 2: If no valid bare array found, scan markdown code fences
    (```json ... ``` or ``` ... ```) for a valid JSON list.

    Returns None if no valid JSON array is found anywhere in the text.

    Requirements: 53-REQ-4.1, 53-REQ-4.E1
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

    return None


def _scan_bracket_arrays(text: str) -> list[dict] | None:
    """Scan text left-to-right for bracket-delimited JSON arrays.

    Uses ``json.JSONDecoder.raw_decode()`` to properly handle brackets
    inside JSON strings, nested objects, and other edge cases. Returns the
    first valid JSON list found starting at a ``[`` character, or None.
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

        # Advance past the opening bracket and try the next one
        pos = start + 1

    return None


# ---------------------------------------------------------------------------
# Typed parse functions (53-REQ-4.2)
# ---------------------------------------------------------------------------


def parse_review_findings(
    json_objects: list[dict],
    spec_name: str,
    task_group: int | str,
    session_id: str,
) -> list[ReviewFinding]:
    """Parse a list of dicts into ReviewFinding instances.

    Required fields: ``severity``, ``description``.
    Optional fields: ``requirement_ref``.
    Objects missing required fields are skipped with a warning log.

    Requirements: 53-REQ-4.2
    """
    results: list[ReviewFinding] = []
    for obj in json_objects:
        if not isinstance(obj, dict):
            logger.warning(
                "Skipping non-dict item in review findings: %r", type(obj).__name__
            )
            continue
        if "severity" not in obj or "description" not in obj:
            logger.warning(
                "Skipping review finding: missing required field(s) "
                "(severity, description). Got keys: %s",
                list(obj.keys()),
            )
            continue
        results.append(
            ReviewFinding(
                id=str(uuid.uuid4()),
                severity=obj["severity"],
                description=obj["description"],
                requirement_ref=obj.get("requirement_ref"),
                spec_name=spec_name,
                task_group=task_group,  # type: ignore[arg-type]
                session_id=session_id,
            )
        )
    return results


def parse_verification_results(
    json_objects: list[dict],
    spec_name: str,
    task_group: int | str,
    session_id: str,
) -> list[VerificationResult]:
    """Parse a list of dicts into VerificationResult instances.

    Required fields: ``requirement_id``, ``verdict`` (must be PASS or FAIL).
    Optional fields: ``evidence``.
    Objects with missing or invalid fields are skipped with a warning log.

    Requirements: 53-REQ-4.2
    """
    results: list[VerificationResult] = []
    for obj in json_objects:
        if not isinstance(obj, dict):
            logger.warning(
                "Skipping non-dict item in verification results: %r",
                type(obj).__name__,
            )
            continue
        if "requirement_id" not in obj:
            logger.warning(
                "Skipping verification result: missing required field "
                "'requirement_id'. Got keys: %s",
                list(obj.keys()),
            )
            continue
        if "verdict" not in obj:
            logger.warning(
                "Skipping verification result: missing required field "
                "'verdict'. Got keys: %s",
                list(obj.keys()),
            )
            continue
        verdict_val = str(obj["verdict"]).upper().strip()
        if verdict_val not in VALID_VERDICTS:
            logger.warning(
                "Skipping verification result: invalid verdict '%s' "
                "(must be PASS or FAIL)",
                obj["verdict"],
            )
            continue
        results.append(
            VerificationResult(
                id=str(uuid.uuid4()),
                requirement_id=obj["requirement_id"],
                verdict=verdict_val,
                evidence=obj.get("evidence"),
                spec_name=spec_name,
                task_group=task_group,  # type: ignore[arg-type]
                session_id=session_id,
            )
        )
    return results


def parse_drift_findings(
    json_objects: list[dict],
    spec_name: str,
    task_group: int | str,
    session_id: str,
) -> list[DriftFinding]:
    """Parse a list of dicts into DriftFinding instances.

    Required fields: ``severity``, ``description``.
    Optional fields: ``spec_ref``, ``artifact_ref``.
    Objects missing required fields are skipped with a warning log.

    Requirements: 53-REQ-4.2
    """
    results: list[DriftFinding] = []
    for obj in json_objects:
        if not isinstance(obj, dict):
            logger.warning(
                "Skipping non-dict item in drift findings: %r", type(obj).__name__
            )
            continue
        if "severity" not in obj or "description" not in obj:
            logger.warning(
                "Skipping drift finding: missing required field(s) "
                "(severity, description). Got keys: %s",
                list(obj.keys()),
            )
            continue
        results.append(
            DriftFinding(
                id=str(uuid.uuid4()),
                severity=obj["severity"],
                description=obj["description"],
                spec_ref=obj.get("spec_ref"),
                artifact_ref=obj.get("artifact_ref"),
                spec_name=spec_name,
                task_group=task_group,  # type: ignore[arg-type]
                session_id=session_id,
            )
        )
    return results
