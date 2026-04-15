"""Parse structured JSON output from review archetype agents.

Extracts JSON blocks from agent response text, validates against expected
schemas, normalizes fields, and produces typed dataclass instances for DB
ingestion.

Combines output-level parsing (JSON extraction, fuzzy key matching, legacy
formats) with item-level typed parsing (field validation, truncation,
normalization into ReviewFinding / VerificationResult / DriftFinding).

Requirements: 27-REQ-3.1, 27-REQ-3.2, 27-REQ-3.3, 27-REQ-3.E1, 27-REQ-3.E2
             53-REQ-4.1, 53-REQ-4.2, 53-REQ-4.E1
             74-REQ-2.1, 74-REQ-2.2, 74-REQ-2.3, 74-REQ-2.4
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_fox.nightshift.fix_types import FixReviewResult, TriageResult
    from agent_fox.session.convergence import AuditResult

from agent_fox.core.json_extraction import extract_json_array
from agent_fox.core.llm_validation import (
    MAX_CONTENT_LENGTH,
    MAX_EVIDENCE_LENGTH,
    MAX_REF_LENGTH,
    truncate_field,
)
from agent_fox.knowledge.audit import AuditEvent, AuditEventType, AuditSeverity
from agent_fox.knowledge.review_store import (
    VALID_VERDICTS,
    DriftFinding,
    ReviewFinding,
    VerificationResult,
    normalize_severity,
    validate_verdict,
)

# Re-export for backward compatibility with consumers
__all__ = ["extract_json_array"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Security keyword detection for automatic category classification
# ---------------------------------------------------------------------------

_SECURITY_KEYWORDS: frozenset[str] = frozenset(
    {
        "command injection",
        "sql injection",
        "sqli",
        "xss",
        "cross-site scripting",
        "path traversal",
        "directory traversal",
        "remote code execution",
        "rce",
        "ssrf",
        "server-side request forgery",
        "open redirect",
        "xxe",
        "xml injection",
        "ldap injection",
        "code injection",
        "shell injection",
        "injection vulnerability",
        "privilege escalation",
        "arbitrary command",
        "arbitrary code",
    }
)


def _detect_security_category(description: str) -> str | None:
    """Return 'security' if the description contains security-related keywords.

    Case-insensitive substring match against a known set of security keywords.
    Returns None if no security keywords are found.
    """
    lower = description.lower()
    for keyword in _SECURITY_KEYWORDS:
        if keyword in lower:
            return "security"
    return None


# ---------------------------------------------------------------------------
# Field-level key normalization (74-REQ-2.4)
# ---------------------------------------------------------------------------


def _normalize_keys(obj: dict) -> dict:
    """Lowercase all keys in *obj* (non-recursive, one level only).

    Allows typed parsers to accept non-standard key casing from LLM output
    (e.g., ``"Severity"`` or ``"DESCRIPTION"``).

    If two keys collide after lowercasing, the last one wins (standard Python
    dict behaviour).

    Requirements: 74-REQ-2.4
    """
    return {k.lower(): v for k, v in obj.items()}


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
            logger.warning("Skipping non-dict item in review findings: %r", type(obj).__name__)
            continue
        obj = _normalize_keys(obj)
        if "severity" not in obj or "description" not in obj:
            logger.warning(
                "Skipping review finding: missing required field(s) (severity, description). Got keys: %s",
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
            req_ref = truncate_field(req_ref, max_length=MAX_REF_LENGTH, field_name="finding.requirement_ref")
        category = _detect_security_category(description)
        results.append(
            ReviewFinding(
                id=str(uuid.uuid4()),
                severity=normalize_severity(obj["severity"]),
                description=description,
                requirement_ref=req_ref,
                spec_name=spec_name,
                task_group=task_group,  # type: ignore[arg-type]
                session_id=session_id,
                category=category,
            )
        )
    return results


def parse_verification_results(
    json_objects: list[dict],
    spec_name: str,
    task_group: int | str,
    session_id: str,
    *,
    emit_audit_event: Callable[[AuditEvent], None] | None = None,
) -> list[VerificationResult]:
    """Parse a list of dicts into VerificationResult instances.

    Required fields: ``requirement_id``, ``verdict`` (PASS or FAIL).
    Optional fields: ``evidence``.
    Objects missing required fields are skipped with a warning log.

    Non-standard verdict values (e.g. ``PARTIAL``, ``CONDITIONAL``) are
    normalized to ``FAIL`` rather than dropped. When *emit_audit_event* is
    provided, a :data:`~agent_fox.knowledge.audit.AuditEventType.VERDICT_NORMALIZED`
    event is emitted for each coerced verdict so operators can observe the
    normalization.

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
        obj = _normalize_keys(obj)
        if "requirement_id" not in obj:
            logger.warning(
                "Skipping verification result: missing required field 'requirement_id'. Got keys: %s",
                list(obj.keys()),
            )
            continue
        if "verdict" not in obj:
            logger.warning(
                "Skipping verification result: missing required field 'verdict'. Got keys: %s",
                list(obj.keys()),
            )
            continue
        raw_verdict = str(obj["verdict"])
        verdict_val = validate_verdict(raw_verdict)
        original_upper = raw_verdict.upper().strip()
        verdict_was_coerced = original_upper not in VALID_VERDICTS

        req_id = truncate_field(
            str(obj["requirement_id"]),
            max_length=MAX_REF_LENGTH,
            field_name="verdict.requirement_id",
        )

        if verdict_was_coerced and emit_audit_event is not None:
            emit_audit_event(
                AuditEvent(
                    run_id="",
                    event_type=AuditEventType.VERDICT_NORMALIZED,
                    severity=AuditSeverity.WARNING,
                    session_id=session_id,
                    payload={
                        "original_verdict": original_upper,
                        "normalized_verdict": verdict_val,
                        "requirement_id": req_id,
                    },
                )
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
            logger.warning("Skipping non-dict item in drift findings: %r", type(obj).__name__)
            continue
        obj = _normalize_keys(obj)
        if "severity" not in obj or "description" not in obj:
            logger.warning(
                "Skipping drift finding: missing required field(s) (severity, description). Got keys: %s",
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
            spec_ref = truncate_field(spec_ref, max_length=MAX_REF_LENGTH, field_name="drift.spec_ref")
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
    "acceptance_criteria": {"acceptance_criteria", "criteria", "test_cases"},
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


# Regex for markdown code fences (```json ... ``` or ``` ... ```)
_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)


def _extract_json_blocks(text: str) -> list[str]:
    """Extract JSON blocks from mixed prose/JSON agent output.

    Handles fenced code blocks (``\u0060\u0060\u0060json ... \u0060\u0060\u0060``) and bare JSON
    objects/arrays embedded in prose.  Uses ``json.JSONDecoder.raw_decode()``
    for correct handling of braces and brackets inside JSON string values
    (e.g. ``/repos/{owner}/{repo}/labels``).

    Requirements: 27-REQ-3.1, 27-REQ-3.2
    """
    blocks: list[str] = []

    # Pass 1: fenced code blocks — common LLM output despite bare-JSON prompts.
    # Record their spans so pass 2 can skip over them.
    fenced_spans: list[tuple[int, int]] = []
    for match in _FENCE_RE.finditer(text):
        fenced_spans.append((match.start(), match.end()))
        content = match.group(1).strip()
        if content:
            blocks.append(content)

    # Pass 2: scan for bare JSON objects/arrays using raw_decode.
    # Unlike the old regex, raw_decode correctly handles braces inside
    # JSON string values, nested structures of arbitrary depth, etc.
    # Skip positions inside fenced code blocks to avoid duplicates.
    decoder = json.JSONDecoder()
    pos = 0
    text_len = len(text)
    while pos < text_len:
        # Skip over fenced code block regions.
        in_fence = False
        for fence_start, fence_end in fenced_spans:
            if fence_start <= pos < fence_end:
                pos = fence_end
                in_fence = True
                break
        if in_fence:
            continue
        if pos >= text_len:
            break

        ch = text[pos]
        if ch in ("{", "["):
            try:
                _, end_idx = decoder.raw_decode(text, pos)
                blocks.append(text[pos:end_idx])
                pos = end_idx
                continue
            except (json.JSONDecodeError, ValueError):
                pass
        pos += 1

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

    Parsing strategy (in order):
    - Direct ``json.loads`` on the full response (handles bare JSON output
      and complex nested structures whose string values may contain brace
      characters that confuse the regex).
    - Regex-based block extraction (handles fenced code blocks and bare
      JSON objects/arrays in mixed prose responses).

    Requirements: 46-REQ-8.1
    """
    from agent_fox.session.convergence import AuditEntry, AuditResult

    def _build_audit_result(data: object) -> AuditResult | None:
        """Convert a parsed JSON value into an AuditResult, or return None."""
        if not isinstance(data, dict):
            return None
        audit_key = _resolve_wrapper_key(data, "audit")
        if audit_key is None:
            return None

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

    # ------------------------------------------------------------------
    # Fast path: try direct JSON parsing on the entire response.
    # The auditor prompt instructs bare JSON output with no fences, so this
    # path handles conforming responses without regex overhead.
    # ------------------------------------------------------------------
    stripped = response.strip()
    try:
        direct = json.loads(stripped)
        result = _build_audit_result(direct)
        if result is not None:
            return result
        # A recognisable JSON value was found but yielded no audit key.
        # For bare-JSON responses stop here to avoid double-counting.
        if stripped.startswith(("{", "[")):
            logger.warning("No valid audit result extracted from Auditor output")
            return None
    except json.JSONDecodeError:
        pass

    # ------------------------------------------------------------------
    # Fallback: regex-based block extraction.
    # Handles fenced code blocks and mixed prose/JSON responses.
    # ------------------------------------------------------------------
    blocks = _extract_json_blocks(response)

    if not blocks:
        logger.warning("No valid JSON blocks found in Auditor output")
        return None

    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue

        result = _build_audit_result(data)
        if result is not None:
            return result

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


# ---------------------------------------------------------------------------
# Triage and fix-reviewer parsers (82-REQ-2.1 .. 82-REQ-2.E1, 82-REQ-5.1)
# ---------------------------------------------------------------------------

_TRIAGE_REQUIRED_KEYS = ("id", "description", "preconditions", "expected", "assertion")


def _dump_parse_failure(response: str, session_id: str, parser_type: str) -> None:
    """Write raw agent response to .agent-fox/ for debugging.

    Only call this when verbose mode is active (DEBUG logging enabled).
    Best-effort: I/O errors are logged at DEBUG level and swallowed so the
    caller is never interrupted by file-system issues.

    The file is named ``parse_failure_{parser_type}_{safe_session_id}_{ts}.txt``
    and written into the ``.agent-fox/`` directory in the current working tree.
    """
    safe_id = re.sub(r"[:/\\]", "_", session_id)
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S")
    filename = f"parse_failure_{parser_type}_{safe_id}_{ts}.txt"
    path = Path(".agent-fox") / filename
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(response, encoding="utf-8")
        logger.debug("Raw agent response written to %s", path)
    except OSError:
        logger.debug("Failed to write parse failure dump to %s", path, exc_info=True)


def parse_triage_output(
    response: str,
    spec_name: str,
    session_id: str,
) -> TriageResult:
    """Parse triage JSON into TriageResult.

    Returns empty TriageResult on parse failure.

    Requirements: 82-REQ-2.1, 82-REQ-2.2, 82-REQ-2.3, 82-REQ-2.E1
    """
    from agent_fox.nightshift.fix_types import AcceptanceCriterion, TriageResult

    # Try direct JSON parse first, then regex fallback via _extract_json_blocks
    data: dict | None = None
    stripped = response.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            data = parsed
    except json.JSONDecodeError:
        pass

    if data is None:
        # Fallback: extract from fenced code blocks or bare JSON
        blocks = _extract_json_blocks(response)
        for block in blocks:
            try:
                parsed = json.loads(block)
                if isinstance(parsed, dict):
                    data = parsed
                    break
            except json.JSONDecodeError:
                continue

    if data is None:
        logger.warning(
            "No parseable JSON in triage output for %s (session %s)",
            spec_name,
            session_id,
        )
        if logger.isEnabledFor(logging.DEBUG):
            _dump_parse_failure(response, session_id, "triage")
        return TriageResult()

    summary = data.get("summary", "")
    if not isinstance(summary, str):
        summary = ""

    affected_files = data.get("affected_files", [])
    if not isinstance(affected_files, list):
        affected_files = []
    affected_files = [f for f in affected_files if isinstance(f, str)]

    # Resolve the criteria array using fuzzy wrapper key matching
    criteria_key = _resolve_wrapper_key(data, "acceptance_criteria")
    raw_criteria = data.get(criteria_key, []) if criteria_key else []
    if not isinstance(raw_criteria, list):
        raw_criteria = []

    criteria: list[AcceptanceCriterion] = []
    for item in raw_criteria:
        if not isinstance(item, dict):
            continue
        # All five fields must be present and non-empty
        if not all(isinstance(item.get(k), str) and item[k] for k in _TRIAGE_REQUIRED_KEYS):
            continue
        criteria.append(
            AcceptanceCriterion(
                id=item["id"],
                description=item["description"],
                preconditions=item["preconditions"],
                expected=item["expected"],
                assertion=item["assertion"],
            )
        )

    return TriageResult(
        summary=summary,
        affected_files=affected_files,
        criteria=criteria,
    )


def parse_fix_review_output(
    response: str,
    spec_name: str,
    session_id: str,
) -> FixReviewResult:
    """Parse fix reviewer JSON into FixReviewResult.

    Returns FixReviewResult with overall_verdict='FAIL' on parse failure.

    Requirements: 82-REQ-5.1
    """
    from agent_fox.nightshift.fix_types import FixReviewResult, FixReviewVerdict

    _VALID_VERDICTS = {"PASS", "FAIL"}

    # Try direct JSON parse first, then regex fallback
    data: dict | None = None
    stripped = response.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            data = parsed
    except json.JSONDecodeError:
        pass

    if data is None:
        blocks = _extract_json_blocks(response)
        for block in blocks:
            try:
                parsed = json.loads(block)
                if isinstance(parsed, dict):
                    data = parsed
                    break
            except json.JSONDecodeError:
                continue

    if data is None:
        logger.warning(
            "No parseable JSON in fix reviewer output for %s (session %s)",
            spec_name,
            session_id,
        )
        if logger.isEnabledFor(logging.DEBUG):
            _dump_parse_failure(response, session_id, "fix_review")
        return FixReviewResult(is_parse_failure=True)

    # Extract verdicts using fuzzy wrapper key
    verdicts_key = _resolve_wrapper_key(data, "verdicts")
    raw_verdicts = data.get(verdicts_key, []) if verdicts_key else []
    if not isinstance(raw_verdicts, list):
        raw_verdicts = []

    verdicts: list[FixReviewVerdict] = []
    for item in raw_verdicts:
        if not isinstance(item, dict):
            continue
        criterion_id = item.get("criterion_id", "")
        verdict_val = item.get("verdict", "")
        evidence = item.get("evidence", "")
        if not isinstance(verdict_val, str) or verdict_val not in _VALID_VERDICTS:
            continue
        if not isinstance(criterion_id, str):
            continue
        if not isinstance(evidence, str):
            evidence = str(evidence)
        verdicts.append(
            FixReviewVerdict(
                criterion_id=criterion_id,
                verdict=verdict_val,
                evidence=evidence,
            )
        )

    summary = data.get("summary", "")
    if not isinstance(summary, str):
        summary = ""

    overall_verdict = data.get("overall_verdict", "FAIL")
    if not isinstance(overall_verdict, str) or overall_verdict not in _VALID_VERDICTS:
        overall_verdict = "FAIL"

    # Enforce: if any individual verdict is FAIL, overall must be FAIL
    if any(v.verdict == "FAIL" for v in verdicts):
        overall_verdict = "FAIL"

    return FixReviewResult(
        verdicts=verdicts,
        overall_verdict=overall_verdict,
        summary=summary,
    )
