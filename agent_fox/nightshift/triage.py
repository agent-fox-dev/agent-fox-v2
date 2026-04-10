"""AI batch triage: prompt construction, response parsing, order recommendation.

Requirements: 71-REQ-3.1, 71-REQ-3.2, 71-REQ-3.3, 71-REQ-3.E1, 71-REQ-3.E2
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent_fox.core.json_extraction import extract_json_object
from agent_fox.core.prompt_safety import sanitize_prompt_content
from agent_fox.nightshift.dep_graph import DependencyEdge
from agent_fox.platform.github import IssueResult

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
    """Internal: run the actual AI triage call using ADVANCED model tier.

    Requirements: 71-REQ-3.2 (ADVANCED tier)
    """
    from agent_fox.core.client import (
        cached_messages_create,
        create_async_anthropic_client,
    )
    from agent_fox.core.models import resolve_model
    from agent_fox.core.retry import retry_api_call_async
    from agent_fox.core.token_tracker import track_response_usage

    model_entry = resolve_model("ADVANCED")
    prompt = _build_triage_prompt(issues, explicit_edges)

    async def _call() -> object:
        client = create_async_anthropic_client()
        return await cached_messages_create(
            client,
            model=model_entry.model_id,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

    try:
        response = await retry_api_call_async(_call, context="batch triage")
    except Exception as exc:
        from agent_fox.nightshift.cost_helpers import emit_auxiliary_cost_fail

        emit_auxiliary_cost_fail(sink, run_id, "batch_triage", exc, model_entry.model_id)
        raise

    track_response_usage(response, model_entry.model_id, "batch triage")

    # Emit cost for this auxiliary AI call (91-REQ-4.2)
    from agent_fox.core.config import PricingConfig
    from agent_fox.nightshift.cost_helpers import emit_auxiliary_cost

    pricing = getattr(config, "pricing", PricingConfig())
    emit_auxiliary_cost(sink, run_id, "batch_triage", response, model_entry.model_id, pricing)

    # Extract text from response
    first_block = response.content[0]  # type: ignore[attr-defined]
    response_text = getattr(first_block, "text", None)
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
    """Run ADVANCED-tier AI analysis on the fix batch.

    Raises TriageError on failure (caller falls back to explicit refs).

    Requirements: 71-REQ-3.1, 71-REQ-3.2, 71-REQ-3.3
    """
    try:
        return await _run_ai_triage(issues, explicit_edges, config, sink=sink, run_id=run_id)
    except TriageError:
        raise
    except Exception as exc:
        raise TriageError(f"AI triage failed: {exc}") from exc
