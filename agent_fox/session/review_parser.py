"""Parse structured JSON output from Skeptic/Verifier agents.

Extracts JSON blocks from agent response text, validates against expected
schemas, and produces typed dataclass instances for DB ingestion.

Requirements: 27-REQ-3.1, 27-REQ-3.2, 27-REQ-3.3, 27-REQ-3.E1, 27-REQ-3.E2
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from agent_fox.knowledge.review_store import (
    VALID_SEVERITIES,
    VALID_VERDICTS,
    DriftFinding,
    ReviewFinding,
    VerificationResult,
)

logger = logging.getLogger(__name__)

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


def _normalize_severity(severity: str) -> str:
    """Normalize severity to a valid value.

    Requirements: 27-REQ-3.E2
    """
    normalized = severity.lower().strip()
    if normalized in VALID_SEVERITIES:
        return normalized
    logger.warning("Unknown severity '%s', normalizing to 'observation'", severity)
    return "observation"


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
    findings: list[ReviewFinding] = []
    blocks = _extract_json_blocks(response)

    if not blocks:
        logger.warning("No valid JSON blocks found in Skeptic output")
        return findings

    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON block in Skeptic output, skipping")
            continue

        # Handle {"findings": [...]} wrapper or bare array
        items: list[dict] = []
        if isinstance(data, dict) and "findings" in data:
            items = data["findings"]
        elif isinstance(data, list):
            items = data
        elif isinstance(data, dict) and "severity" in data:
            items = [data]
        else:
            continue

        for item in items:
            if not isinstance(item, dict):
                logger.warning("Non-dict finding item, skipping")
                continue
            if "severity" not in item or "description" not in item:
                logger.warning(
                    "Finding missing required fields (severity, description), skipping"
                )
                continue

            findings.append(
                ReviewFinding(
                    id=str(uuid.uuid4()),
                    severity=_normalize_severity(item["severity"]),
                    description=item["description"],
                    requirement_ref=item.get("requirement_ref"),
                    spec_name=spec_name,
                    task_group=task_group,
                    session_id=session_id,
                )
            )

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
    verdicts: list[VerificationResult] = []
    blocks = _extract_json_blocks(response)

    if not blocks:
        logger.warning("No valid JSON blocks found in Verifier output")
        return verdicts

    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON block in Verifier output, skipping")
            continue

        # Handle {"verdicts": [...]} wrapper or bare array
        items: list[dict] = []
        if isinstance(data, dict) and "verdicts" in data:
            items = data["verdicts"]
        elif isinstance(data, list):
            items = data
        elif isinstance(data, dict) and "requirement_id" in data:
            items = [data]
        else:
            continue

        for item in items:
            if not isinstance(item, dict):
                logger.warning("Non-dict verdict item, skipping")
                continue
            if "requirement_id" not in item or "verdict" not in item:
                logger.warning(
                    "Verdict missing required fields "
                    "(requirement_id, verdict), skipping"
                )
                continue

            verdict_val = item["verdict"].upper().strip()
            if verdict_val not in VALID_VERDICTS:
                logger.warning("Invalid verdict '%s', skipping", item["verdict"])
                continue

            verdicts.append(
                VerificationResult(
                    id=str(uuid.uuid4()),
                    requirement_id=item["requirement_id"],
                    verdict=verdict_val,
                    evidence=item.get("evidence"),
                    spec_name=spec_name,
                    task_group=task_group,
                    session_id=session_id,
                )
            )

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
    findings: list[DriftFinding] = []
    blocks = _extract_json_blocks(response)

    if not blocks:
        logger.warning("No valid JSON blocks found in Oracle output")
        return findings

    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON block in Oracle output, skipping")
            continue

        # Handle {"drift_findings": [...]} wrapper or bare array
        items: list[dict] = []
        if isinstance(data, dict) and "drift_findings" in data:
            items = data["drift_findings"]
        elif isinstance(data, list):
            items = data
        elif isinstance(data, dict) and "severity" in data and "description" in data:
            items = [data]
        else:
            continue

        for item in items:
            if not isinstance(item, dict):
                logger.warning("Non-dict drift finding item, skipping")
                continue
            if "severity" not in item or "description" not in item:
                logger.warning(
                    "Drift finding missing required fields "
                    "(severity, description), skipping"
                )
                continue

            findings.append(
                DriftFinding(
                    id=str(uuid.uuid4()),
                    severity=_normalize_severity(item["severity"]),
                    description=item["description"],
                    spec_ref=item.get("spec_ref"),
                    artifact_ref=item.get("artifact_ref"),
                    spec_name=spec_name,
                    task_group=task_group,
                    session_id=session_id,
                )
            )

    if not findings:
        logger.warning("No valid drift findings extracted from Oracle output")

    return findings


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
            severity = _normalize_severity(match.group(1))
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
