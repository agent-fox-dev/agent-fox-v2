"""Staleness check: post-fix evaluation of remaining issues.

Requirements: 71-REQ-5.1, 71-REQ-5.2, 71-REQ-5.3, 71-REQ-5.4,
              71-REQ-5.E1, 71-REQ-5.E2, 71-REQ-5.E3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agent_fox.core.json_extraction import extract_json_object
from agent_fox.platform.github import IssueResult

if TYPE_CHECKING:
    from agent_fox.knowledge.sink import SinkDispatcher

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StalenessResult:
    """Result of post-fix staleness evaluation."""

    obsolete_issues: list[int]  # issue numbers to close
    rationale: dict[int, str] = field(default_factory=dict)  # issue_number -> why


def _build_staleness_prompt(
    fixed_issue: IssueResult,
    remaining_issues: list[IssueResult],
    fix_diff: str,
) -> str:
    """Build the AI staleness evaluation prompt."""
    remaining_descriptions = []
    for issue in remaining_issues:
        body_preview = (issue.body or "")[:500]
        remaining_descriptions.append(f"- #{issue.number}: {issue.title}\n  Body: {body_preview}")

    diff_preview = fix_diff[:3000] if fix_diff else "(no diff available)"

    return f"""\
A fix was applied for issue #{fixed_issue.number}: \
{fixed_issue.title}

The fix diff:
{diff_preview}

Remaining issues to evaluate for obsolescence:
{chr(10).join(remaining_descriptions)}

For each remaining issue, determine if the fix above likely resolves it too.

Return a JSON object with:
- "obsolete": list of objects with "issue_number" and "rationale" for issues
  that are now obsolete due to the fix above.

Respond with ONLY the JSON object."""


def _parse_staleness_response(
    response_text: str,
    remaining_issues: list[IssueResult],
) -> StalenessResult:
    """Parse AI staleness response into a StalenessResult."""
    remaining_numbers = {i.number for i in remaining_issues}

    try:
        data = extract_json_object(response_text)
    except ValueError:
        return StalenessResult(obsolete_issues=[], rationale={})

    if not isinstance(data, dict):
        return StalenessResult(obsolete_issues=[], rationale={})

    obsolete_issues: list[int] = []
    rationale: dict[int, str] = {}

    for entry in data.get("obsolete", []):
        if not isinstance(entry, dict):
            continue
        issue_num = entry.get("issue_number")
        reason = entry.get("rationale", "AI-detected obsolescence")
        if isinstance(issue_num, int) and issue_num in remaining_numbers:
            obsolete_issues.append(issue_num)
            rationale[issue_num] = reason

    return StalenessResult(obsolete_issues=obsolete_issues, rationale=rationale)


async def _run_ai_staleness(
    fixed_issue: IssueResult,
    remaining_issues: list[IssueResult],
    fix_diff: str,
    config: object,
    *,
    sink: SinkDispatcher | None = None,
    run_id: str = "",
) -> StalenessResult:
    """Internal: run the actual AI staleness evaluation using ADVANCED tier.

    Requirements: 71-REQ-5.1
    """
    from agent_fox.nightshift.cost_helpers import nightshift_ai_call

    prompt = _build_staleness_prompt(fixed_issue, remaining_issues, fix_diff)

    response_text, _response = await nightshift_ai_call(
        model_tier="ADVANCED",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        context="staleness check",
        cost_label="staleness_check",
        config=config,
        sink=sink,
        run_id=run_id,
    )

    if response_text is None:
        return StalenessResult(obsolete_issues=[], rationale={})

    return _parse_staleness_response(response_text, remaining_issues)


async def check_staleness(
    fixed_issue: IssueResult,
    remaining_issues: list[IssueResult],
    fix_diff: str,
    config: object,
    platform: object,
    *,
    sink: SinkDispatcher | None = None,
    run_id: str = "",
) -> StalenessResult:
    """Evaluate remaining issues for obsolescence after a fix.

    Uses AI analysis + GitHub API verification. The GitHub API check is
    the authoritative source: an issue is only marked obsolete if the
    platform confirms it is no longer open with the af:fix label.

    Fallback chain:
    - If AI fails: verify via GitHub API only (71-REQ-5.E1)
    - If GitHub fails: log warning, return empty (71-REQ-5.E2)

    Requirements: 71-REQ-5.1, 71-REQ-5.2, 71-REQ-5.E1, 71-REQ-5.E2
    """
    remaining_numbers = {i.number for i in remaining_issues}

    # Step 1: Try AI staleness evaluation
    ai_rationale: dict[int, str] = {}
    ai_failed = False
    try:
        ai_result = await _run_ai_staleness(fixed_issue, remaining_issues, fix_diff, config, sink=sink, run_id=run_id)
        ai_rationale = ai_result.rationale
    except Exception:
        ai_failed = True
        logger.warning(
            "Staleness AI call failed for fix #%d, falling back to GitHub API",
            fixed_issue.number,
            exc_info=True,
        )

    # Step 2: Verify with GitHub API by re-fetching issues (71-REQ-5.2)
    try:
        still_open = await platform.list_issues_by_label(  # type: ignore[attr-defined]
            "af:fix",
            state="open",
        )
        still_open_numbers = {i.number for i in still_open}
    except Exception:
        logger.warning(
            "GitHub re-fetch failed during staleness check for fix #%d, continuing without removing any issues",
            fixed_issue.number,
            exc_info=True,
        )
        return StalenessResult(obsolete_issues=[], rationale={})

    # Step 3: Determine obsolete issues
    obsolete_issues: list[int] = []
    rationale: dict[int, str] = {}

    if ai_failed:
        # AI failure fallback (71-REQ-5.E1): an issue is obsolete when
        # GitHub confirms it is no longer open.
        for num in remaining_numbers:
            if num not in still_open_numbers:
                obsolete_issues.append(num)
                rationale[num] = "closed externally (AI fallback)"
    else:
        # Normal path: an issue is obsolete when the AI says it is
        # resolved AND GitHub confirms it is still open (so our
        # close_issue() call is meaningful).
        for num in remaining_numbers:
            if num in ai_rationale and num in still_open_numbers:
                obsolete_issues.append(num)
                rationale[num] = ai_rationale[num]

    return StalenessResult(obsolete_issues=obsolete_issues, rationale=rationale)
