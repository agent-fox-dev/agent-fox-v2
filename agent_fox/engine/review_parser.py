"""JSON extraction and typed parsing for review archetype output.

Provides `extract_json_array()` to extract a JSON array from LLM output text
(handling prose, markdown fences, and bare arrays), and typed parse functions
that convert raw dicts into ReviewFinding, VerificationResult, and DriftFinding
dataclass instances.

Requirements: 53-REQ-4.1, 53-REQ-4.2, 53-REQ-4.E1
"""

from __future__ import annotations

import logging
import uuid

from agent_fox.core.json_extraction import extract_json_array
from agent_fox.core.llm_validation import (
    MAX_CONTENT_LENGTH,
    MAX_EVIDENCE_LENGTH,
    MAX_REF_LENGTH,
    truncate_field,
)
from agent_fox.knowledge.review_store import (
    DriftFinding,
    ReviewFinding,
    VerificationResult,
    normalize_severity,
    validate_verdict,
)

logger = logging.getLogger(__name__)

# Re-export for backward compatibility with tests and consumers
__all__ = ["extract_json_array"]


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
        description = truncate_field(
            obj["description"],
            max_length=MAX_CONTENT_LENGTH,
            field_name="finding.description",
        )
        req_ref = obj.get("requirement_ref")
        if isinstance(req_ref, str):
            req_ref = truncate_field(
                req_ref, max_length=MAX_REF_LENGTH, field_name="finding.requirement_ref"
            )
        results.append(
            ReviewFinding(
                id=str(uuid.uuid4()),
                severity=normalize_severity(obj["severity"]),
                description=description,
                requirement_ref=req_ref,
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
        verdict_val = validate_verdict(str(obj["verdict"]))
        if verdict_val is None:
            continue
        req_id = truncate_field(
            str(obj["requirement_id"]),
            max_length=MAX_REF_LENGTH,
            field_name="verdict.requirement_id",
        )
        evidence = obj.get("evidence")
        if isinstance(evidence, str):
            evidence = truncate_field(
                evidence,
                max_length=MAX_EVIDENCE_LENGTH,
                field_name="verdict.evidence",
            )
        results.append(
            VerificationResult(
                id=str(uuid.uuid4()),
                requirement_id=req_id,
                verdict=verdict_val,
                evidence=evidence,
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
        description = truncate_field(
            obj["description"],
            max_length=MAX_CONTENT_LENGTH,
            field_name="drift.description",
        )
        spec_ref = obj.get("spec_ref")
        if isinstance(spec_ref, str):
            spec_ref = truncate_field(
                spec_ref, max_length=MAX_REF_LENGTH, field_name="drift.spec_ref"
            )
        artifact_ref = obj.get("artifact_ref")
        if isinstance(artifact_ref, str):
            artifact_ref = truncate_field(
                artifact_ref,
                max_length=MAX_REF_LENGTH,
                field_name="drift.artifact_ref",
            )
        results.append(
            DriftFinding(
                id=str(uuid.uuid4()),
                severity=normalize_severity(obj["severity"]),
                description=description,
                spec_ref=spec_ref,
                artifact_ref=artifact_ref,
                spec_name=spec_name,
                task_group=task_group,  # type: ignore[arg-type]
                session_id=session_id,
            )
        )
    return results
