"""AI-powered semantic analysis for specification validation.

Requirements: 09-REQ-8.1, 09-REQ-8.2, 09-REQ-8.3, 09-REQ-8.E1
             21-REQ-1.*, 21-REQ-2.*, 21-REQ-3.*
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from anthropic.types import TextBlock

from agent_fox.core.client import create_async_anthropic_client
from agent_fox.spec.discovery import SpecInfo  # noqa: F401
from agent_fox.spec.parser import _DEP_TABLE_HEADER_ALT, _TABLE_SEP
from agent_fox.spec.validator import (
    SEVERITY_HINT,
    SEVERITY_WARNING,
    Finding,
)

logger = logging.getLogger(__name__)

# -- JSON extraction from AI responses ----------------------------------------

_JSON_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Parse JSON from an AI response, stripping markdown code fences if present.

    Tries raw parsing first, then falls back to extracting fenced blocks.
    Raises json.JSONDecodeError or TypeError on failure.
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # Try extracting from code fences
    match = _JSON_FENCE.search(text)
    if match:
        return json.loads(match.group(1))
    raise json.JSONDecodeError("No JSON found in AI response", text, 0)


# -- Backtick extraction regex ------------------------------------------------

_BACKTICK_TOKEN = re.compile(r"`([^`]+)`")

# -- Stale-dependency data model -----------------------------------------------


@dataclass(frozen=True)
class DependencyRef:
    """A code identifier extracted from a dependency Relationship cell.

    Requirements: 21-REQ-1.1
    """

    declaring_spec: str  # spec that declares the dependency
    upstream_spec: str  # spec being depended on
    identifier: str  # extracted code identifier (normalized)
    raw_relationship: str  # original Relationship text for context


def _normalize_identifier(raw: str) -> str:
    """Normalize a backtick-extracted identifier.

    - Strip trailing parentheses: ``Delete()`` -> ``Delete``
    - Preserve dotted paths as-is.

    Requirements: 21-REQ-1.2, 21-REQ-1.3
    """
    if raw.endswith("()"):
        return raw[:-2]
    return raw


def extract_relationship_identifiers(
    declaring_spec: str,
    prd_path: Path,
) -> list[DependencyRef]:
    """Extract backtick-delimited code identifiers from dependency tables.

    Parses prd.md for the alternative dependency table format
    (| Spec | From Group | To Group | Relationship |) and extracts all
    backtick-delimited tokens from the Relationship column.

    Normalization:
    - Strip trailing parentheses: ``Delete()`` -> ``Delete``
    - Preserve dotted paths: ``store.SnippetStore.Delete`` stays as-is

    Returns an empty list if no dependency table or no backtick tokens found.

    Requirements: 21-REQ-1.1, 21-REQ-1.2, 21-REQ-1.3, 21-REQ-1.E1, 21-REQ-1.E2
    """
    if not prd_path.is_file():
        return []

    text = prd_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    refs: list[DependencyRef] = []

    for i, line in enumerate(lines):
        if not _DEP_TABLE_HEADER_ALT.search(line):
            continue

        # Parse data rows after header
        for row_line in lines[i + 1 :]:
            if _TABLE_SEP.match(row_line):
                continue
            stripped = row_line.strip()
            if not stripped.startswith("|"):
                break

            cells = [c.strip() for c in stripped.split("|")]
            cells = [c for c in cells if c]
            if len(cells) < 4:
                continue

            upstream_spec = cells[0].strip()
            relationship = cells[3].strip()

            if not upstream_spec or not relationship:
                continue

            # Extract backtick tokens from the Relationship column
            tokens = _BACKTICK_TOKEN.findall(relationship)
            for token in tokens:
                identifier = _normalize_identifier(token)
                refs.append(
                    DependencyRef(
                        declaring_spec=declaring_spec,
                        upstream_spec=upstream_spec,
                        identifier=identifier,
                        raw_relationship=relationship,
                    )
                )

    return refs


# -- Stale-dependency AI prompt ------------------------------------------------

_STALE_DEP_PROMPT = """\
You are an expert software architect reviewing specification documents. \
You will be given a design document from an upstream specification and a \
list of code identifiers that downstream specifications claim to depend on.

For each identifier, determine whether the upstream design document defines, \
describes, or reasonably implies that identifier. Consider:
- Exact name matches (type, function, method, struct, interface)
- Qualified names (e.g., `store.Store` matching a `Store` type in a \
  `store` package section)
- Method references (e.g., `Store.Delete` matching a `Delete` method on \
  `Store`)
- Standard library or language built-ins (e.g., `error`, `context.Context`, \
  `slog`) should be marked as "found" since they are not defined in specs

Return your analysis as a JSON object with this exact structure:
{{
  "results": [
    {{
      "identifier": "the identifier being checked",
      "found": true or false,
      "explanation": "brief reason why it was or was not found",
      "suggestion": "if not found, a suggested correction or null"
    }}
  ]
}}

Upstream design document ({upstream_spec}):

{design_content}

---

Identifiers to validate:
{identifiers_json}
"""

_RULE_STALE_DEP = "stale-dependency"


async def validate_dependency_interfaces(
    upstream_spec: str,
    design_content: str,
    refs: list[DependencyRef],
    model: str,
) -> list[Finding]:
    """Validate dependency identifiers against an upstream design document.

    Sends a single AI request per upstream spec containing the design.md
    content and all identifiers referencing that spec. Parses the
    structured JSON response and produces Warning-severity findings for
    identifiers the AI determines are not present.

    Requirements: 21-REQ-2.1, 21-REQ-2.3, 21-REQ-2.4, 21-REQ-2.5,
                  21-REQ-2.E3
    """
    identifiers = [r.identifier for r in refs]
    identifiers_json = json.dumps(identifiers)

    prompt = _STALE_DEP_PROMPT.format(
        upstream_spec=upstream_spec,
        design_content=design_content,
        identifiers_json=identifiers_json,
    )

    async with create_async_anthropic_client() as client:
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

    # Extract text from response
    first_block = response.content[0]
    if isinstance(first_block, TextBlock):
        response_text: str = first_block.text
    else:
        maybe_text: str | None = getattr(first_block, "text", None)
        if maybe_text is None:
            logger.warning(
                "AI response for stale-dep check on '%s' has no text, skipping",
                upstream_spec,
            )
            return []
        response_text = maybe_text

    try:
        data = _extract_json(response_text)
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "AI response for stale-dep check on '%s' was not valid JSON, skipping",
            upstream_spec,
        )
        return []

    results = data.get("results", [])
    if not isinstance(results, list):
        logger.warning(
            "AI response for stale-dep check on '%s' has invalid 'results', skipping",
            upstream_spec,
        )
        return []

    # Build a lookup from identifier -> DependencyRef(s) for finding context
    ref_by_id: dict[str, DependencyRef] = {}
    for ref in refs:
        if ref.identifier not in ref_by_id:
            ref_by_id[ref.identifier] = ref

    findings: list[Finding] = []
    for result in results:
        if not isinstance(result, dict):
            continue

        identifier = result.get("identifier", "")
        found = result.get("found", True)
        explanation = result.get("explanation", "")
        suggestion = result.get("suggestion")

        if found:
            continue

        # Look up the declaring spec from the ref
        matched_ref = ref_by_id.get(identifier)
        declaring_spec = matched_ref.declaring_spec if matched_ref else "unknown"

        suggestion_text = suggestion if suggestion else ""
        message = (
            f"Dependency on {upstream_spec}: identifier `{identifier}` "
            f"not found in design.md. {explanation}."
        )
        if suggestion_text:
            message += f" Suggestion: {suggestion_text}"

        findings.append(
            Finding(
                spec_name=declaring_spec,
                file="prd.md",
                rule=_RULE_STALE_DEP,
                severity=SEVERITY_WARNING,
                message=message,
                line=None,
            )
        )

    return findings


async def run_stale_dependency_validation(
    discovered_specs: list[SpecInfo],
    specs_dir: Path,
    model: str,
) -> list[Finding]:
    """Run stale-dependency validation across all discovered specs.

    Algorithm:
    1. For each spec with a prd.md, extract dependency identifiers.
    2. Group identifiers by upstream spec name.
    3. For each upstream spec group:
       a. Read the upstream spec's design.md (once per upstream spec).
       b. If design.md doesn't exist, skip (no finding).
       c. Call validate_dependency_interfaces() with all refs for that
          upstream spec.
    4. Collect and return all findings.

    If the AI model is unavailable, log a warning and return empty list.

    Requirements: 21-REQ-2.2, 21-REQ-2.E1, 21-REQ-2.E2, 21-REQ-3.1,
                  21-REQ-3.2, 21-REQ-3.E1
    """
    # 1. Extract all dependency identifiers from all specs
    all_refs: list[DependencyRef] = []
    for spec in discovered_specs:
        prd_path = spec.path / "prd.md"
        if not prd_path.is_file():
            continue
        refs = extract_relationship_identifiers(spec.name, prd_path)
        all_refs.extend(refs)

    if not all_refs:
        return []

    # 2. Group by upstream spec
    by_upstream: dict[str, list[DependencyRef]] = defaultdict(list)
    for ref in all_refs:
        by_upstream[ref.upstream_spec].append(ref)

    # 3. Validate each upstream spec
    findings: list[Finding] = []
    for upstream_name, refs in by_upstream.items():
        design_path = specs_dir / upstream_name / "design.md"
        if not design_path.is_file():
            continue  # 21-REQ-2.E1: skip if design.md missing

        design_content = design_path.read_text(encoding="utf-8")

        try:
            upstream_findings = await validate_dependency_interfaces(
                upstream_name, design_content, refs, model
            )
            findings.extend(upstream_findings)
        except Exception as exc:
            logger.warning(
                "Stale-dependency validation failed for upstream '%s': %s. Skipping.",
                upstream_name,
                exc,
            )

    return findings


# -- Existing AI validation rules -----------------------------------------------

# Rule names for AI-detected issues
_RULE_VAGUE = "vague-criterion"
_RULE_IMPLEMENTATION_LEAK = "implementation-leak"

# Map from AI response issue_type to rule name
_ISSUE_TYPE_TO_RULE = {
    "vague": _RULE_VAGUE,
    "implementation-leak": _RULE_IMPLEMENTATION_LEAK,
}

_AI_PROMPT = """\
You are an expert specification reviewer. Analyze the following acceptance \
criteria from a software specification and identify quality issues.

For each criterion, check for two types of problems:
1. **Vague or unmeasurable** criteria: Criteria that use subjective language \
like "should be fast", "look good", "easy to use", "performant", etc. These \
cannot be objectively verified.
2. **Implementation-leaking** criteria: Criteria that describe HOW the system \
should be built (implementation details) rather than WHAT it should do \
(behavior). For example, "use Redis for caching" or "implement with a \
singleton pattern".

Return your analysis as a JSON object with this exact structure:
{
  "issues": [
    {
      "criterion_id": "the requirement ID, e.g. 09-REQ-1.1",
      "issue_type": "vague" or "implementation-leak",
      "explanation": "why this criterion is problematic",
      "suggestion": "how to improve it"
    }
  ]
}

If there are no issues, return: {"issues": []}

Here are the acceptance criteria to analyze:

"""


async def analyze_acceptance_criteria(
    spec_name: str,
    spec_path: Path,
    model: str,
) -> list[Finding]:
    """Use AI to analyze acceptance criteria for quality issues.

    Reads requirements.md, extracts acceptance criteria text, and sends
    it to the STANDARD-tier model for analysis.

    The prompt asks the model to identify:
    1. Vague or unmeasurable criteria (rule: vague-criterion)
    2. Implementation-leaking criteria (rule: implementation-leak)

    Returns Hint-severity findings for each issue identified.
    """
    req_path = spec_path / "requirements.md"
    if not req_path.is_file():
        return []

    req_text = req_path.read_text(encoding="utf-8")

    # Create the Anthropic client and send the request
    async with create_async_anthropic_client() as client:
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": _AI_PROMPT + req_text,
                }
            ],
        )

    # Parse the response — narrow the content block union to TextBlock
    first_block = response.content[0]
    if isinstance(first_block, TextBlock):
        response_text: str = first_block.text
    else:
        # Fallback for types with a .text attribute (e.g. test mocks)
        maybe_text: str | None = getattr(first_block, "text", None)
        if maybe_text is None:
            logger.warning(
                "AI response for spec '%s' has no text content, skipping",
                spec_name,
            )
            return []
        response_text = maybe_text

    try:
        data = _extract_json(response_text)
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "AI response for spec '%s' was not valid JSON, skipping",
            spec_name,
        )
        return []

    issues = data.get("issues", [])
    if not isinstance(issues, list):
        logger.warning(
            "AI response for spec '%s' has invalid 'issues' field, skipping",
            spec_name,
        )
        return []

    findings: list[Finding] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue

        criterion_id = issue.get("criterion_id", "unknown")
        issue_type = issue.get("issue_type", "")
        explanation = issue.get("explanation", "")
        suggestion = issue.get("suggestion", "")

        rule = _ISSUE_TYPE_TO_RULE.get(issue_type)
        if rule is None:
            continue

        message = f"[{criterion_id}] {explanation}"
        if suggestion:
            message += f" Suggestion: {suggestion}"

        findings.append(
            Finding(
                spec_name=spec_name,
                file="requirements.md",
                rule=rule,
                severity=SEVERITY_HINT,
                message=message,
                line=None,
            )
        )

    return findings


# -- AI rewrite prompt and function (Spec 22) ---------------------------------

_REWRITE_PROMPT = """\
You are an expert requirements engineer using the EARS (Easy Approach to \
Requirements Syntax) methodology. You will rewrite acceptance criteria that \
have been flagged for quality issues.

EARS syntax uses these keywords:
- SHALL — for unconditional requirements
- WHEN <trigger>, THE system SHALL — for event-driven requirements
- WHILE <state>, THE system SHALL — for state-driven requirements
- IF <condition>, THEN THE system SHALL — for conditional requirements
- WHERE <feature>, THE system SHALL — for feature-driven requirements

Rules for rewriting:
1. Use EARS syntax keywords (SHALL, WHEN, WHILE, IF/THEN, WHERE) in every \
rewritten criterion.
2. Preserve the original intent and behavioral scope — only fix the \
identified quality issue (vagueness or implementation leak).
3. Produce text that would pass the vague-criterion and implementation-leak \
analysis rules and would not be flagged again.
4. Make criteria measurable and objectively verifiable.
5. Do NOT include the requirement ID prefix in the replacement text — \
only provide the criterion body.

Return your rewrites as a JSON object with this exact structure:
{{
  "rewrites": [
    {{
      "criterion_id": "the requirement ID, e.g. 09-REQ-1.1",
      "original": "the original criterion text",
      "replacement": "the rewritten criterion text"
    }}
  ]
}}

Here is the full requirements document for context:

{requirements_text}

---

The following criteria have been flagged for rewriting:

{flagged_criteria}
"""

_MAX_CRITERIA_PER_BATCH = 20


async def rewrite_criteria(
    spec_name: str,
    requirements_text: str,
    findings: list[Finding],
    model: str,
) -> dict[str, str]:
    """Send a batched rewrite request for flagged criteria.

    Args:
        spec_name: Name of the spec being fixed.
        requirements_text: Full content of requirements.md.
        findings: AI findings with rule vague-criterion or implementation-leak.
        model: Model ID for the STANDARD tier.

    Returns:
        Mapping of criterion_id -> replacement_text.
        Empty dict on failure.

    Requirements: 22-REQ-1.1, 22-REQ-2.*, 22-REQ-3.*
    """
    if not findings:
        return {}

    # Build the flagged criteria list for the prompt
    flagged_lines: list[str] = []
    for finding in findings:
        flagged_lines.append(
            f"- Criterion {finding.message.split(']')[0].lstrip('[')}]: "
            f"Issue type: {finding.rule}. {finding.message}"
        )

    flagged_criteria = "\n".join(flagged_lines)

    prompt = _REWRITE_PROMPT.format(
        requirements_text=requirements_text,
        flagged_criteria=flagged_criteria,
    )

    try:
        async with create_async_anthropic_client() as client:
            response = await client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
    except Exception as exc:
        logger.warning(
            "AI rewrite call failed for spec '%s': %s. Skipping rewrite.",
            spec_name,
            exc,
        )
        return {}

    # Extract text from response
    first_block = response.content[0]
    if isinstance(first_block, TextBlock):
        response_text: str = first_block.text
    else:
        maybe_text: str | None = getattr(first_block, "text", None)
        if maybe_text is None:
            logger.warning(
                "AI rewrite response for spec '%s' has no text, skipping",
                spec_name,
            )
            return {}
        response_text = maybe_text

    try:
        data = _extract_json(response_text)
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "AI rewrite response for spec '%s' was not valid JSON, skipping",
            spec_name,
        )
        return {}

    rewrites_list = data.get("rewrites", [])
    if not isinstance(rewrites_list, list):
        logger.warning(
            "AI rewrite response for spec '%s' has invalid 'rewrites', skipping",
            spec_name,
        )
        return {}

    # Build the result mapping
    result: dict[str, str] = {}
    for entry in rewrites_list:
        if not isinstance(entry, dict):
            continue
        criterion_id = entry.get("criterion_id", "")
        replacement = entry.get("replacement", "")
        if criterion_id and replacement:
            result[criterion_id] = replacement

    return result


async def run_ai_validation(
    discovered_specs: list[SpecInfo],
    model: str,
    specs_dir: Path | None = None,
) -> list[Finding]:
    """Run AI validation across all discovered specs.

    Runs both the existing acceptance criteria analysis and the new
    stale-dependency validation. The specs_dir parameter is needed for
    the stale-dependency rule to locate upstream design.md files.

    If the AI model is unavailable (auth error, network error), logs a
    warning and returns an empty list.

    Requirements: 21-REQ-4.1
    """
    findings: list[Finding] = []

    for spec in discovered_specs:
        req_path = spec.path / "requirements.md"
        if not req_path.is_file():
            continue

        try:
            spec_findings = await analyze_acceptance_criteria(
                spec.name, spec.path, model
            )
            findings.extend(spec_findings)
        except Exception as exc:
            logger.warning(
                "AI analysis unavailable for spec '%s': %s. Skipping AI checks.",
                spec.name,
                exc,
            )
            return []

    # NEW: stale-dependency validation (21-REQ-4.1)
    if specs_dir is not None:
        try:
            stale_findings = await run_stale_dependency_validation(
                discovered_specs, specs_dir, model
            )
            findings.extend(stale_findings)
        except Exception as exc:
            logger.warning(
                "Stale-dependency validation unavailable: %s. Skipping.",
                exc,
            )

    return findings
