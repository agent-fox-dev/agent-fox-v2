"""Parse structured JSON output from Skeptic/Verifier agents.

Extracts JSON blocks from agent response text, validates against expected
schemas, and produces typed dataclass instances for DB ingestion.

Item-level validation and dataclass construction is delegated to
:mod:`agent_fox.engine.review_parser` to avoid duplicating field
validation, truncation, and normalization logic.

Requirements: 27-REQ-3.1, 27-REQ-3.2, 27-REQ-3.3, 27-REQ-3.E1, 27-REQ-3.E2
             74-REQ-2.1, 74-REQ-2.2, 74-REQ-2.3
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_fox.session.convergence import AuditResult

from agent_fox.engine.review_parser import (
    parse_drift_findings,
    parse_review_findings,
    parse_verification_results,
)
from agent_fox.knowledge.review_store import (
    DriftFinding,
    ReviewFinding,
    VerificationResult,
    normalize_severity,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fuzzy wrapper key matching (74-REQ-2.1, 74-REQ-2.2, 74-REQ-2.3)
# ---------------------------------------------------------------------------

# Canonical wrapper keys and their accepted variants (case-insensitive lookup
# is applied by _resolve_wrapper_key, so all entries here are lowercase).
WRAPPER_KEY_VARIANTS: dict[str, set[str]] = {
    "findings": {"findings", "finding", "results", "issues"},
    "verdicts": {"verdicts", "verdict", "results", "verifications"},
    "drift_findings": {"drift_findings", "drift_finding", "drifts"},
    "audit": {"audit", "audits", "audit_results", "entries"},
}


def _resolve_wrapper_key(data: dict, canonical_key: str) -> str | None:
    """Find a matching wrapper key in *data*, case-insensitively, with variants.

    Checks all registered variants of *canonical_key* (from
    :data:`WRAPPER_KEY_VARIANTS`) against the actual keys in *data* using
    case-insensitive comparison.  Returns the **actual key** as it appears in
    *data* (preserving its original casing), or ``None`` if no match is found.

    Requirements: 74-REQ-2.1, 74-REQ-2.2, 74-REQ-2.3
    """
    variants = WRAPPER_KEY_VARIANTS.get(canonical_key, {canonical_key})
    # Build a case-folded map from lowercased actual key → original key
    lower_map: dict[str, str] = {k.lower(): k for k in data.keys()}
    for variant in variants:
        actual = lower_map.get(variant.lower())
        if actual is not None:
            return actual
    return None


# Match fenced JSON code blocks or bare JSON objects/arrays
_JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*\n(.*?)\n\s*```"  # fenced code blocks
    r"|(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})"  # bare JSON objects
    r"|(\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\])",  # bare JSON arrays
    re.DOTALL,
)


def _extract_json_blocks(text: str) -> list[str]:
    """Extract JSON blocks from mixed prose/JSON agent output.

    Handles fenced code blocks (```json ... ```) and bare JSON objects/arrays.

    Requirements: 27-REQ-3.1, 27-REQ-3.2
    """
    blocks: list[str] = []
    for match in _JSON_BLOCK_RE.finditer(text):
        # match groups: (1) fenced content, (2) bare object, (3) bare array
        content = match.group(1) or match.group(2) or match.group(3)
        if content:
            blocks.append(content.strip())
    return blocks


def _unwrap_items(
    response: str,
    wrapper_key: str,
    single_item_keys: tuple[str, ...],
    archetype_label: str,
) -> list[dict]:
    """Extract item dicts from agent response text.

    Handles three JSON shapes:
    1. Wrapper object: ``{wrapper_key: [...]}`` (fuzzy key match)
    2. Bare array: ``[{...}, ...]``
    3. Single object containing all *single_item_keys*: ``{...}``

    Returns an empty list if no valid items are found.

    Parsing strategy (in order):
    - Direct ``json.loads`` on the full response (handles complex nested JSON
      whose string values may contain brace characters that confuse the regex).
    - Regex-based block extraction (handles multi-block responses with
      surrounding prose).

    Requirements: 74-REQ-2.3, 74-REQ-2.E1, 74-REQ-2.E2
    """

    def _process_data(data: object) -> list[dict]:
        """Convert a parsed JSON value into a list of item dicts."""
        if isinstance(data, dict):
            resolved_key = _resolve_wrapper_key(data, wrapper_key)
            if resolved_key is not None:
                return list(data[resolved_key])
            if all(k in data for k in single_item_keys):
                return [data]
            return []
        if isinstance(data, list):
            return list(data)
        return []

    # ------------------------------------------------------------------
    # Fast path: try direct JSON parsing on the entire response.
    # This correctly handles JSON strings that contain brace characters.
    # ------------------------------------------------------------------
    stripped = response.strip()
    try:
        direct = json.loads(stripped)
        items = _process_data(direct)
        if items:
            return items
        # A recognisable JSON value was found but yielded no items.
        # For single-document responses with an unknown wrapper key we stop
        # here rather than falling through, to avoid double-counting.
        if stripped.startswith(("{", "[")):
            return items
    except json.JSONDecodeError:
        pass

    # ------------------------------------------------------------------
    # Fallback: regex-based block extraction.
    # Handles responses with multiple JSON blocks interleaved with prose.
    # ------------------------------------------------------------------
    blocks = _extract_json_blocks(response)
    if not blocks:
        logger.warning("No valid JSON blocks found in %s output", archetype_label)
        return []

    all_items: list[dict] = []
    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON block in %s output, skipping", archetype_label)
            continue
        all_items.extend(_process_data(data))

    return all_items


def parse_review_output(
    response: str,
    spec_name: str,
    task_group: str,
    session_id: str,
) -> list[ReviewFinding]:
    """Extract ReviewFinding objects from agent response JSON.

    Looks for a JSON object with a "findings" array, or a bare JSON array
    of finding objects. Each finding must have "severity" and "description".

    Returns empty list if no valid JSON found (27-REQ-3.E1).

    Requirements: 27-REQ-3.1, 27-REQ-3.3, 27-REQ-3.E1, 27-REQ-3.E2
    """
    items = _unwrap_items(response, "findings", ("severity",), "Skeptic")
    findings = parse_review_findings(items, spec_name, task_group, session_id)
    if not findings:
        logger.warning("No valid findings extracted from Skeptic output")
    return findings


def parse_verification_output(
    response: str,
    spec_name: str,
    task_group: str,
    session_id: str,
) -> list[VerificationResult]:
    """Extract VerificationResult objects from agent response JSON.

    Looks for a JSON object with a "verdicts" array, or a bare JSON array
    of verdict objects. Each verdict must have "requirement_id" and "verdict".

    Returns empty list if no valid JSON found (27-REQ-3.E1).

    Requirements: 27-REQ-3.2, 27-REQ-3.3, 27-REQ-3.E1
    """
    items = _unwrap_items(response, "verdicts", ("requirement_id",), "Verifier")
    verdicts = parse_verification_results(items, spec_name, task_group, session_id)
    if not verdicts:
        logger.warning("No valid verdicts extracted from Verifier output")
    return verdicts


def parse_oracle_output(
    response: str,
    spec_name: str,
    task_group: str,
    session_id: str,
) -> list[DriftFinding]:
    """Extract DriftFinding objects from oracle agent response JSON.

    Looks for a JSON object with a "drift_findings" array. Each entry
    must have "severity" and "description". Returns empty list if no
    valid JSON found.

    Requirements: 32-REQ-6.1, 32-REQ-6.2, 32-REQ-6.E1, 32-REQ-6.E2
    """
    items = _unwrap_items(response, "drift_findings", ("severity", "description"), "Oracle")
    findings = parse_drift_findings(items, spec_name, task_group, session_id)
    if not findings:
        logger.warning("No valid drift findings extracted from Oracle output")
    return findings


def parse_auditor_output(
    response: str,
) -> AuditResult | None:
    """Extract an AuditResult from auditor agent response JSON.

    Looks for a JSON object with an "audit" array, "overall_verdict",
    and "summary". Returns None if no valid JSON found.

    Requirements: 46-REQ-8.1
    """
    from agent_fox.session.convergence import AuditEntry, AuditResult

    blocks = _extract_json_blocks(response)

    if not blocks:
        logger.warning("No valid JSON blocks found in Auditor output")
        return None

    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue

        if not isinstance(data, dict):
            continue
        audit_key = _resolve_wrapper_key(data, "audit")
        if audit_key is None:
            continue

        entries: list[AuditEntry] = []
        for item in data[audit_key]:
            if not isinstance(item, dict) or "ts_entry" not in item:
                continue
            entries.append(
                AuditEntry(
                    ts_entry=item["ts_entry"],
                    test_functions=item.get("test_functions", []),
                    verdict=item.get("verdict", "MISSING"),
                    notes=item.get("notes"),
                )
            )

        overall = data.get("overall_verdict", "FAIL")
        summary = data.get("summary", "")

        return AuditResult(
            entries=entries,
            overall_verdict=overall,
            summary=summary,
        )

    logger.warning("No valid audit result extracted from Auditor output")
    return None


def parse_legacy_review_md(
    content: str,
    spec_name: str,
    task_group: str,
    session_id: str,
) -> list[ReviewFinding]:
    """Parse a legacy review.md file into ReviewFinding records.

    Extracts findings in the format:
    - [severity: X] description

    Requirements: 27-REQ-10.1, 27-REQ-10.E1
    """
    findings: list[ReviewFinding] = []
    pattern = re.compile(r"- \[severity:\s*(\w+)\]\s*(.+)")

    for line in content.splitlines():
        match = pattern.match(line.strip())
        if match:
            severity = normalize_severity(match.group(1))
            description = match.group(2).strip()
            findings.append(
                ReviewFinding(
                    id=str(uuid.uuid4()),
                    severity=severity,
                    description=description,
                    requirement_ref=None,
                    spec_name=spec_name,
                    task_group=task_group,
                    session_id=session_id,
                )
            )

    return findings


def parse_legacy_verification_md(
    content: str,
    spec_name: str,
    task_group: str,
    session_id: str,
) -> list[VerificationResult]:
    """Parse a legacy verification.md file into VerificationResult records.

    Extracts verdicts from markdown table rows:
    | requirement_id | PASS/FAIL | notes |

    Requirements: 27-REQ-10.2, 27-REQ-10.E1
    """
    verdicts: list[VerificationResult] = []
    # Match table rows: | XX-REQ-N.N | PASS/FAIL | notes |
    pattern = re.compile(r"\|\s*(\S+-REQ-\S+)\s*\|\s*(PASS|FAIL)\s*\|\s*(.*?)\s*\|")

    for line in content.splitlines():
        match = pattern.search(line)
        if match:
            req_id = match.group(1).strip()
            verdict = match.group(2).strip().upper()
            evidence = match.group(3).strip() or None
            verdicts.append(
                VerificationResult(
                    id=str(uuid.uuid4()),
                    requirement_id=req_id,
                    verdict=verdict,
                    evidence=evidence,
                    spec_name=spec_name,
                    task_group=task_group,
                    session_id=session_id,
                )
            )

    return verdicts
