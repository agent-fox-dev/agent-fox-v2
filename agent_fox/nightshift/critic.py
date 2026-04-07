"""Cross-category finding consolidation critic.

Replaces the mechanical consolidate_findings() from finding.py with an
AI-powered critic stage that deduplicates, validates evidence, calibrates
severity, and synthesises coherent FindingGroups across categories.

Requirements: 73-REQ-1.1 through 73-REQ-7.E1
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from agent_fox.core.json_extraction import extract_json_object
from agent_fox.nightshift.finding import Finding, FindingGroup

logger = logging.getLogger(__name__)

# Minimum number of findings required to trigger the AI critic stage.
# Batches below this threshold use mechanical grouping instead.
MINIMUM_FINDING_THRESHOLD: int = 3


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CriticDecision:
    """A single decision made by the critic stage.

    Requirements: 73-REQ-6.1, 73-REQ-6.2, 73-REQ-6.3
    """

    action: str  # "merged" | "dropped" | "severity_changed"
    finding_indices: list[int]  # Indices into the original findings list
    reason: str  # Human-readable justification
    original_severity: str | None  # For severity_changed actions
    new_severity: str | None  # For severity_changed actions


@dataclass(frozen=True)
class CriticSummary:
    """Summary statistics for the critic run.

    Requirements: 73-REQ-6.3
    """

    total_received: int
    total_dropped: int
    total_merged: int  # Findings that were merged (not groups produced)
    groups_produced: int


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


async def consolidate_findings(
    findings: list[Finding],
) -> list[FindingGroup]:
    """Replace for the old consolidate_findings() from finding.py.

    If len(findings) == 0, returns an empty list immediately.
    If len(findings) < MINIMUM_FINDING_THRESHOLD, uses mechanical grouping.
    Otherwise, runs the AI critic stage with mechanical fallback on failure.

    Returns a list of FindingGroups ready for issue creation.

    Requirements: 73-REQ-4.1, 73-REQ-4.2, 73-REQ-4.E1, 73-REQ-7.2, 73-REQ-7.3
    """
    if not findings:
        return []

    if len(findings) < MINIMUM_FINDING_THRESHOLD:
        return _mechanical_grouping(findings)

    # Critic path — fall back to mechanical on any failure.
    try:
        response_text = await _run_critic(findings)
    except Exception as exc:
        logger.warning(
            "Critic AI backend failed; falling back to mechanical grouping: %s",
            exc,
        )
        return _mechanical_grouping(findings)

    try:
        groups, decisions = _parse_critic_response(response_text, findings)
    except ValueError as exc:
        logger.warning(
            "Critic returned malformed response; falling back to mechanical grouping: %s",
            exc,
        )
        return _mechanical_grouping(findings)

    # Compute summary statistics.
    dropped_count = sum(len(d.finding_indices) for d in decisions if d.action == "dropped")
    # "merged" findings are those that appear in groups with more than one finding.
    merged_count = sum(len(g.findings) for g in groups if len(g.findings) > 1)
    summary = CriticSummary(
        total_received=len(findings),
        total_dropped=dropped_count,
        total_merged=merged_count,
        groups_produced=len(groups),
    )

    _log_decisions(decisions, summary)
    return groups


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _mechanical_grouping(findings: list[Finding]) -> list[FindingGroup]:
    """Fallback: each finding becomes its own FindingGroup.

    Requirements: 73-REQ-4.2, 73-REQ-5.1, 73-REQ-5.3
    """
    groups: list[FindingGroup] = []
    for finding in findings:
        affected = sorted(set(finding.affected_files))
        body = _build_body(finding.description, finding.severity, affected)
        groups.append(
            FindingGroup(
                findings=[finding],
                title=finding.title,
                body=body,
                category=finding.category,
                affected_files=affected,
            )
        )
    return groups


async def _run_critic(findings: list[Finding]) -> str:
    """Send findings to Claude for cross-category consolidation.

    Returns the raw AI response text.
    Raises on AI backend failure.

    Requirements: 73-REQ-7.3
    """
    from agent_fox.core.client import (
        cached_messages_create,
        create_async_anthropic_client,
    )
    from agent_fox.core.models import resolve_model
    from agent_fox.core.retry import retry_api_call_async
    from agent_fox.core.token_tracker import track_response_usage

    model_entry = resolve_model("ADVANCED")
    user_message = _build_critic_user_message(findings)

    logger.debug("Critic system prompt:\n%s", _CRITIC_SYSTEM_PROMPT)
    logger.debug("Critic user message:\n%s", user_message)

    async def _call() -> object:
        client = create_async_anthropic_client()
        return await cached_messages_create(
            client,
            model=model_entry.model_id,
            max_tokens=8192,
            system=_CRITIC_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

    response = await retry_api_call_async(_call, context="finding consolidation critic")
    track_response_usage(response, model_entry.model_id, "finding consolidation critic")

    first_block = response.content[0]  # type: ignore[attr-defined]
    response_text = getattr(first_block, "text", None)
    if response_text is None:
        raise ValueError("AI critic response has no text content")

    logger.debug("Critic raw response:\n%s", response_text)
    return response_text


def _parse_critic_response(
    response_text: str,
    findings: list[Finding],
) -> tuple[list[FindingGroup], list[CriticDecision]]:
    """Parse AI JSON response into FindingGroups and CriticDecisions.

    Raises ValueError on malformed JSON.
    Invalid (out-of-bounds) finding indices are skipped with a warning.

    Requirements: 73-REQ-1.2, 73-REQ-1.3, 73-REQ-5.2, 73-REQ-5.3, 73-REQ-5.E2
    """
    data = extract_json_object(response_text)

    raw_groups: list[dict] = data.get("groups", [])
    raw_dropped: list[dict] = data.get("dropped", [])

    decisions: list[CriticDecision] = []
    groups: list[FindingGroup] = []

    for raw_group in raw_groups:
        indices: list[int] = raw_group.get("finding_indices", [])
        title: str = raw_group.get("title", "")
        description: str = raw_group.get("description", "")
        severity: str = raw_group.get("severity", "minor")
        merge_reason: str = raw_group.get("merge_reason", "")

        # Filter out invalid indices.
        valid_indices: list[int] = []
        for idx in indices:
            if 0 <= idx < len(findings):
                valid_indices.append(idx)
            else:
                logger.warning(
                    "Critic response contains out of bounds finding index %d "
                    "(invalid index; findings list has %d entries); skipping.",
                    idx,
                    len(findings),
                )

        if not valid_indices:
            continue

        group_findings = [findings[i] for i in valid_indices]
        affected_files = sorted({fp for f in group_findings for fp in f.affected_files})
        body = _build_body(description, severity, affected_files)

        # Derive a representative category from the first finding.
        category = group_findings[0].category

        groups.append(
            FindingGroup(
                findings=group_findings,
                title=title,
                body=body,
                category=category,
                affected_files=affected_files,
            )
        )

        if len(valid_indices) > 1:
            decisions.append(
                CriticDecision(
                    action="merged",
                    finding_indices=valid_indices,
                    reason=merge_reason,
                    original_severity=None,
                    new_severity=None,
                )
            )

    for raw_drop in raw_dropped:
        idx = raw_drop.get("finding_index", -1)
        reason = raw_drop.get("reason", "")

        if not (0 <= idx < len(findings)):
            logger.warning(
                "Critic dropped entry references out-of-bounds index %d; skipping.",
                idx,
            )
            continue

        decisions.append(
            CriticDecision(
                action="dropped",
                finding_indices=[idx],
                reason=reason,
                original_severity=None,
                new_severity=None,
            )
        )

    return groups, decisions


def _log_decisions(
    decisions: list[CriticDecision],
    summary: CriticSummary,
) -> None:
    """Log all critic decisions at appropriate levels.

    Requirements: 73-REQ-6.1, 73-REQ-6.2, 73-REQ-6.3, 73-REQ-6.4, 73-REQ-6.E1
    """
    try:
        for decision in decisions:
            if decision.action == "dropped":
                logger.info(
                    "Critic dropped findings %s: %s",
                    decision.finding_indices,
                    decision.reason,
                )
            elif decision.action == "merged":
                logger.info(
                    "Critic merged findings %s: %s",
                    decision.finding_indices,
                    decision.reason,
                )
            elif decision.action == "severity_changed":
                logger.info(
                    "Critic changed severity from %s to %s for findings %s: %s",
                    decision.original_severity,
                    decision.new_severity,
                    decision.finding_indices,
                    decision.reason,
                )

        logger.info(
            "Critic summary: received=%d, dropped=%d, merged=%d, groups_produced=%d",
            summary.total_received,
            summary.total_dropped,
            summary.total_merged,
            summary.groups_produced,
        )
    except Exception:  # noqa: BLE001
        # Logging failures must not interrupt the consolidation pipeline.
        # Requirements: 73-REQ-6.E1
        pass


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_CRITIC_SYSTEM_PROMPT: str = """\
You are a code-quality critic reviewing automated hunt findings for a software project.
Your job is to analyse a batch of findings across multiple categories and produce a
deduplicated, validated, and severity-calibrated consolidation for issue creation.

Rules:
1. GROUP findings that share the same root cause or affect overlapping code into a
   single group. Do not split a group just because findings come from different
   categories — the goal is one issue per root cause.
2. VALIDATE evidence. A finding's evidence must contain concrete proof: tool output,
   file:line references, code snippets, or coverage percentages. Evidence that is
   empty or purely speculative (e.g. "might be", "could potentially", "possibly")
   is insufficient — drop that finding.
3. ASSIGN a final severity to each group based on the combined context of all
   findings within the group. Choose from: info, minor, major, critical.
4. Every input finding must appear in exactly one group OR in the dropped list.
   Do not silently omit any finding.

Return ONLY a JSON object (no markdown, no explanation outside the JSON) with:
{
  "groups": [
    {
      "title": "<short synthesised title for the issue>",
      "description": "<synthesised description from all merged findings>",
      "severity": "<info|minor|major|critical>",
      "finding_indices": [<0-based indices of findings in this group>],
      "merge_reason": "<why these findings belong together, or 'Standalone'>"
    }
  ],
  "dropped": [
    {
      "finding_index": <0-based index>,
      "reason": "<brief reason why this finding was dropped>"
    }
  ]
}
"""


def _build_critic_user_message(findings: list[Finding]) -> str:
    """Build the user message for the critic prompt from a list of findings.

    Each finding is serialised as a JSON object with its 0-based index so
    the critic can reference findings by index in its response.

    Requirements: 73-REQ-1.1, 73-REQ-2.1
    """
    items: list[dict[str, object]] = []
    for i, finding in enumerate(findings):
        items.append(
            {
                "index": i,
                "category": finding.category,
                "title": finding.title,
                "description": finding.description,
                "severity": finding.severity,
                "affected_files": finding.affected_files,
                "evidence": finding.evidence,
            }
        )
    return json.dumps({"findings": items}, indent=2)


# ---------------------------------------------------------------------------
# Private utilities
# ---------------------------------------------------------------------------


def _build_body(description: str, severity: str, affected_files: list[str]) -> str:
    """Build a FindingGroup body string from critic-provided fields."""
    lines: list[str] = [description, "", f"**Severity:** {severity}"]
    if affected_files:
        files_str = ", ".join(f"`{f}`" for f in affected_files)
        lines += ["", f"**Affected files:** {files_str}"]
    return "\n".join(lines)
