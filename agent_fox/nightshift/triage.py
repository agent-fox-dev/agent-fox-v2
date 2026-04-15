"""AI batch triage: prompt construction, response parsing, order recommendation.

Uses maintainer:hunt archetype identity for model tier and security config
resolution (100-REQ-2.2, 100-REQ-5.1, 100-REQ-5.2).

Requirements: 71-REQ-3.1, 71-REQ-3.2, 71-REQ-3.3, 71-REQ-3.E1, 71-REQ-3.E2,
              100-REQ-2.2, 100-REQ-5.1, 100-REQ-5.2, 100-REQ-5.3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent_fox.core.json_extraction import extract_json_object
from agent_fox.core.prompt_safety import sanitize_prompt_content
from agent_fox.engine.sdk_params import resolve_model_tier, resolve_security_config
from agent_fox.nightshift.dep_graph import DependencyEdge
from agent_fox.platform.protocol import IssueResult

if TYPE_CHECKING:
    from agent_fox.knowledge.sink import SinkDispatcher

logger = logging.getLogger(__name__)


class TriageError(Exception):
    """Raised when AI triage fails."""


@dataclass(frozen=True)
class TriageResult:
    """Output of AI batch triage."""

    processing_order: list[int]  # recommended issue numbers in order
    edges: list[DependencyEdge]  # AI-detected dependencies
    supersession_pairs: list[tuple[int, int]]  # (keep, obsolete) pairs


def _build_triage_prompt(
    issues: list[IssueResult],
    explicit_edges: list[DependencyEdge],
) -> str:
    """Build the AI triage prompt from issues and known edges."""
    issue_descriptions = []
    for issue in issues:
        body_preview = (issue.body or "")[:500]
        safe_title = sanitize_prompt_content(issue.title, label="issue-title")
        safe_body = sanitize_prompt_content(body_preview, label="issue-body")
        issue_descriptions.append(f"- #{issue.number}: {safe_title}\n  Body: {safe_body}")

    edges_text = ""
    if explicit_edges:
        edge_lines = [
            f"  - #{e.from_issue} must be fixed before #{e.to_issue} ({e.source}: {e.rationale})"
            for e in explicit_edges
        ]
        edges_text = "\nKnown dependency edges:\n" + "\n".join(edge_lines)

    return f"""\
Analyze these GitHub issues labeled af:fix and determine \
the optimal processing order.

Issues:
{chr(10).join(issue_descriptions)}
{edges_text}

Return a JSON object with:
- "processing_order": list of issue numbers in recommended processing order
- "dependencies": list of objects with "from_issue", "to_issue", "rationale"
- "supersession": list of objects with "keep", "obsolete", "rationale"

Consider:
1. Which issues depend on others being fixed first?
2. Which issues might make others obsolete if fixed?
3. What is the optimal order to minimize wasted effort?

Respond with ONLY the JSON object."""


def _parse_triage_response(
    response_text: str,
    issues: list[IssueResult],
) -> TriageResult:
    """Parse AI response text into a TriageResult.

    Raises TriageError if the response cannot be parsed.
    """
    issue_numbers = {i.number for i in issues}

    try:
        data = extract_json_object(response_text)
    except ValueError as exc:
        raise TriageError(f"Failed to parse triage JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise TriageError("AI response is not a JSON object")

    # Parse processing order
    raw_order = data.get("processing_order", [])
    if not isinstance(raw_order, list):
        raise TriageError("processing_order is not a list")
    processing_order = [n for n in raw_order if isinstance(n, int) and n in issue_numbers]

    # Parse dependency edges
    edges: list[DependencyEdge] = []
    for dep in data.get("dependencies", []):
        if not isinstance(dep, dict):
            continue
        from_issue = dep.get("from_issue")
        to_issue = dep.get("to_issue")
        rationale = dep.get("rationale", "AI-detected dependency")
        if (
            isinstance(from_issue, int)
            and isinstance(to_issue, int)
            and from_issue in issue_numbers
            and to_issue in issue_numbers
            and from_issue != to_issue
        ):
            edges.append(DependencyEdge(from_issue, to_issue, "ai", rationale))

    # Parse supersession pairs
    supersession_pairs: list[tuple[int, int]] = []
    for sup in data.get("supersession", []):
        if not isinstance(sup, dict):
            continue
        keep = sup.get("keep")
        obsolete = sup.get("obsolete")
        if isinstance(keep, int) and isinstance(obsolete, int) and keep in issue_numbers and obsolete in issue_numbers:
            supersession_pairs.append((keep, obsolete))

    return TriageResult(
        processing_order=processing_order,
        edges=edges,
        supersession_pairs=supersession_pairs,
    )


async def _run_ai_triage(
    issues: list[IssueResult],
    explicit_edges: list[DependencyEdge],
    config: object,
    *,
    sink: SinkDispatcher | None = None,
    run_id: str = "",
) -> TriageResult:
    """Internal: run the actual AI triage call using maintainer:hunt archetype.

    Resolves model tier and security config from maintainer:hunt archetype
    identity (100-REQ-2.2, 100-REQ-5.1, 100-REQ-5.2).

    Requirements: 71-REQ-3.2, 100-REQ-2.2, 100-REQ-5.1, 100-REQ-5.2, 100-REQ-5.3
    """
    from agent_fox.nightshift.cost_helpers import nightshift_ai_call

    # Resolve model tier and security config via maintainer:hunt archetype identity
    # (100-REQ-5.1, 100-REQ-5.2, 100-REQ-2.2)
    tier = resolve_model_tier(config, "maintainer", mode="hunt")
    _security = resolve_security_config(config, "maintainer", mode="hunt")
    logger.debug(
        "Batch triage using maintainer:hunt — tier=%s, allowlist=%s",
        tier,
        getattr(_security, "bash_allowlist", None),
    )

    prompt = _build_triage_prompt(issues, explicit_edges)

    response_text, _response = await nightshift_ai_call(
        model_tier=tier,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        context="batch triage",
        cost_label="batch_triage",
        config=config,
        sink=sink,
        run_id=run_id,
    )

    if response_text is None:
        raise TriageError("AI response has no text content")

    return _parse_triage_response(response_text, issues)


async def run_batch_triage(
    issues: list[IssueResult],
    explicit_edges: list[DependencyEdge],
    config: object,
    *,
    sink: SinkDispatcher | None = None,
    run_id: str = "",
) -> TriageResult:
    """Run AI analysis on the fix batch using maintainer:hunt archetype identity.

    Model tier and security config are resolved from the maintainer:hunt
    archetype registry entry (100-REQ-2.2, 100-REQ-5.1, 100-REQ-5.2).

    Raises TriageError on failure (caller falls back to explicit refs).

    Requirements: 71-REQ-3.1, 71-REQ-3.2, 71-REQ-3.3, 100-REQ-2.2, 100-REQ-5.1,
                  100-REQ-5.2, 100-REQ-5.3
    """
    try:
        return await _run_ai_triage(issues, explicit_edges, config, sink=sink, run_id=run_id)
    except TriageError:
        raise
    except Exception as exc:
        raise TriageError(f"AI triage failed: {exc}") from exc
