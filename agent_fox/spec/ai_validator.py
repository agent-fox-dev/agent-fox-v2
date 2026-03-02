"""AI-powered semantic analysis for specification validation.

Requirements: 09-REQ-8.1, 09-REQ-8.2, 09-REQ-8.3, 09-REQ-8.E1
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic  # noqa: F401
from anthropic.types import TextBlock

from agent_fox.spec.discovery import SpecInfo  # noqa: F401
from agent_fox.spec.validator import SEVERITY_HINT, Finding  # noqa: F401

logger = logging.getLogger(__name__)

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
    client = anthropic.AsyncAnthropic()
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
        data = json.loads(response_text)
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


async def run_ai_validation(
    discovered_specs: list[SpecInfo],
    model: str,
) -> list[Finding]:
    """Run AI validation across all discovered specs.

    Iterates through specs, calling analyze_acceptance_criteria for each
    spec that has a requirements.md file. Collects and returns all findings.

    If the AI model is unavailable (auth error, network error), logs a
    warning and returns an empty list.
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

    return findings
