"""Phase 2 improve loop for auto-improve.

Orchestrates analyzer, coder, verifier sessions per pass, manages
termination conditions, cost tracking, and rollback.

Requirements: 31-REQ-5.* through 31-REQ-8.*
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.analyzer import (
    build_analyzer_prompt,
    filter_improvements,
    load_review_context,
    parse_analyzer_response,
    query_oracle_context,
)
from agent_fox.fix.checks import CheckDescriptor
from agent_fox.fix.events import FixProgressCallback, make_progress_emitter

logger = logging.getLogger(__name__)

# Initial estimated cost per session, used for budget pre-checks.
# Updated dynamically based on observed session costs.
_INITIAL_SESSION_COST_ESTIMATE = 0.05

# Minimum budget required for a single full pass (analyzer + coder + verifier).
_MIN_PASS_COST = _INITIAL_SESSION_COST_ESTIMATE * 3


class ImproveTermination(StrEnum):
    """Reason the improve loop terminated."""

    CONVERGED = "converged"
    PASS_LIMIT = "pass_limit"
    COST_LIMIT = "cost_limit"
    VERIFIER_FAIL = "verifier_fail"
    INTERRUPTED = "interrupted"
    ANALYZER_ERROR = "analyzer_error"
    CODER_ERROR = "coder_error"


@dataclass
class VerifierVerdict:
    """Parsed verifier verdict."""

    quality_gates: str  # "PASS" or "FAIL"
    improvement_valid: bool
    verdict: str  # "PASS" or "FAIL"
    evidence: str


@dataclass
class ImprovePassResult:
    """Result of a single improvement pass."""

    pass_number: int
    improvements_applied: int
    improvements_by_tier: dict[str, int]
    verifier_verdict: str  # "PASS" or "FAIL"
    analyzer_cost: float
    coder_cost: float
    verifier_cost: float
    rolled_back: bool


@dataclass
class ImproveResult:
    """Result of the entire Phase 2 improve loop."""

    passes_completed: int
    max_passes: int
    total_improvements: int
    improvements_by_tier: dict[str, int]
    verifier_pass_count: int
    verifier_fail_count: int
    sessions_consumed: int
    total_cost: float
    termination_reason: ImproveTermination
    pass_results: list[ImprovePassResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Verifier verdict parsing (31-REQ-6.2, 31-REQ-6.E2)
# ---------------------------------------------------------------------------

_REQUIRED_VERDICT_FIELDS = {"quality_gates", "improvement_valid", "verdict", "evidence"}


def parse_verifier_verdict(response: str) -> VerifierVerdict:
    """Parse the verifier's JSON verdict.

    Raises ValueError on invalid JSON or missing required fields.

    Requirements: 31-REQ-6.2, 31-REQ-6.E2
    """
    try:
        data = json.loads(response)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in verifier response: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Verifier response must be a JSON object")

    missing = _REQUIRED_VERDICT_FIELDS - set(data.keys())
    if missing:
        raise ValueError(f"Verifier response missing required fields: {sorted(missing)}")

    return VerifierVerdict(
        quality_gates=str(data["quality_gates"]),
        improvement_valid=bool(data["improvement_valid"]),
        verdict=str(data["verdict"]),
        evidence=str(data["evidence"]),
    )


# ---------------------------------------------------------------------------
# Git helpers (31-REQ-7.*, 31-REQ-5.E1)
# ---------------------------------------------------------------------------


def rollback_improvement_pass(project_root: Path) -> None:
    """Roll back the most recent commit via git reset --hard HEAD~1.

    Raises on non-zero exit from git.

    Requirements: 31-REQ-7.1, 31-REQ-7.3, 31-REQ-7.E1
    """
    result = subprocess.run(
        ["git", "reset", "--hard", "HEAD~1"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        msg = f"git reset --hard HEAD~1 failed (exit {result.returncode}): {result.stderr}"
        logger.error(msg)
        raise RuntimeError(msg)

    logger.info("Rolled back improvement pass: git reset --hard HEAD~1")


def discard_partial_changes(project_root: Path) -> None:
    """Discard uncommitted changes via git checkout -- .

    Best-effort cleanup; does not raise on failure.

    Requirements: 31-REQ-5.E1
    """
    try:
        subprocess.run(
            ["git", "checkout", "--", "."],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        logger.info("Discarded partial changes: git checkout -- .")
    except Exception:
        logger.warning("Failed to discard partial changes", exc_info=True)


def _create_commit(project_root: Path, pass_number: int, summary: str) -> None:
    """Stage all changes and create a git commit.

    Requirements: 31-REQ-5.4
    """
    # Stage changes
    subprocess.run(
        ["git", "add", "-A"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    # Truncate summary for commit message
    short_summary = summary[:72] if len(summary) > 72 else summary
    message = f"refactor: auto-improve pass {pass_number} - {short_summary}"

    subprocess.run(
        ["git", "commit", "-m", message, "--allow-empty"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Coder / verifier prompt helpers
# ---------------------------------------------------------------------------


def _build_coder_prompt(improvements: list) -> tuple[str, str]:
    """Build system and task prompts for the coder session.

    Requirements: 31-REQ-5.2, 31-REQ-5.3
    """
    system_prompt = (
        "You are an auto-improve coding agent. Implement the improvement plan below.\n"
        "Make minimal, targeted changes that simplify the codebase.\n"
        "\n"
        "## Rules\n"
        "\n"
        "- Implement improvements in the order listed (quick wins first)\n"
        "- Never refactor test code for DRYness\n"
        "- Preserve all public APIs\n"
        '- Preserve "why" comments\n'
        "- Maintain error handling and logging\n"
        "- Favor deletion over addition\n"
        "- Run quality checks after changes to verify correctness"
    )

    plan_lines: list[str] = []
    for imp in improvements:
        plan_lines.append(f"- [{imp.tier}] {imp.title}: {imp.description} (files: {', '.join(imp.files)})")

    task_prompt = (
        "Implement the following improvements:\n\n"
        + "\n".join(plan_lines)
        + "\n\nAfter implementing, verify that all quality checks pass."
    )

    return system_prompt, task_prompt


def _build_verifier_prompt(pass_number: int) -> tuple[str, str]:
    """Build system and task prompts for the verifier session.

    Requirements: 31-REQ-6.1, 31-REQ-6.3
    """
    system_prompt = (
        "You are a code verification agent. Your job is to verify that "
        "recent changes are correct and represent genuine improvements."
    )

    task_prompt = (
        "## Verification Task\n\n"
        f"Verify the changes from auto-improve pass {pass_number}.\n\n"
        "## Quality Gate Check\n\n"
        "Run all detected quality checks. ALL checks must pass.\n\n"
        "## Improvement Validation\n\n"
        "Beyond standard quality gate checks, verify:\n\n"
        "1. No functionality was removed (only simplified or reorganized)\n"
        "2. No public API signatures were changed\n"
        "3. No test coverage was reduced\n"
        "4. The code is measurably simpler or clearer\n"
        "5. Error handling and logging are preserved\n\n"
        "Produce your verdict as JSON:\n\n"
        "{\n"
        '  "quality_gates": "PASS" or "FAIL",\n'
        '  "improvement_valid": true or false,\n'
        '  "verdict": "PASS" or "FAIL",\n'
        '  "evidence": "Summary of findings"\n'
        "}"
    )

    return system_prompt, task_prompt


# ---------------------------------------------------------------------------
# Main improve loop (31-REQ-2.*, 31-REQ-5.*, 31-REQ-6.*, 31-REQ-7.*, 31-REQ-8.*)
# ---------------------------------------------------------------------------


async def run_improve_loop(
    project_root: Path,
    config: AgentFoxConfig,
    checks: list[CheckDescriptor] | None = None,
    max_passes: int = 3,
    remaining_budget: float | None = None,
    phase1_diff: str = "",
    session_runner: Callable[..., Awaitable[tuple[float, str]]] | None = None,
    progress_callback: FixProgressCallback | None = None,
) -> ImproveResult:
    """Run the iterative improvement loop (Phase 2).

    Algorithm:
    1. For each pass (up to max_passes):
       a. Check cost budget for a full pass.
       b. Run the analyzer session.
       c. If diminishing returns or zero actionable improvements: CONVERGED.
       d. Run the coder session with the filtered improvement plan.
       e. Create a git commit.
       f. Run the verifier session.
       g. If PASS: record pass, continue.
       h. If FAIL: rollback commit, terminate with VERIFIER_FAIL.
    2. If all passes completed, terminate with PASS_LIMIT.

    Optional callback (76-REQ-6.2, 76-REQ-6.E1):
    - progress_callback: called with a FixProgressEvent at key lifecycle points
      (analyzer_start/done, coder_start/done, verifier_start/pass/fail, etc.).
    When None, the loop behaves identically to the pre-76 implementation.

    Requirements: 31-REQ-2.2, 31-REQ-2.3, 31-REQ-5.*, 31-REQ-6.*,
                  31-REQ-7.*, 31-REQ-8.*
    """

    _emit = make_progress_emitter("improve", max_passes, progress_callback)

    pass_results: list[ImprovePassResult] = []
    total_cost = 0.0
    total_improvements = 0
    all_tiers: Counter[str] = Counter()
    verifier_pass_count = 0
    verifier_fail_count = 0
    sessions_consumed = 0
    termination_reason = ImproveTermination.PASS_LIMIT
    previous_pass_summary = ""
    # Track max observed session cost for accurate budget checks
    max_session_cost = _INITIAL_SESSION_COST_ESTIMATE

    # Query oracle and review context once before the loop
    oracle_ctx = query_oracle_context(config)
    review_ctx = load_review_context(project_root)

    for pass_number in range(1, max_passes + 1):
        # -- Cost budget check (31-REQ-8.3) --
        if remaining_budget is not None:
            budget_left = remaining_budget - total_cost
            needed = max_session_cost * 3  # analyzer + coder + verifier
            if budget_left < needed:
                termination_reason = ImproveTermination.COST_LIMIT
                break

        analyzer_cost = 0.0
        coder_cost = 0.0
        verifier_cost = 0.0

        try:
            # -- Analyzer (31-REQ-3.*) --
            sys_prompt, task_prompt = build_analyzer_prompt(
                project_root,
                config,
                oracle_context=oracle_ctx,
                review_context=review_ctx,
                phase1_diff=phase1_diff,
                previous_pass_result=previous_pass_summary,
            )

            if session_runner is None:
                termination_reason = ImproveTermination.ANALYZER_ERROR
                break

            # Emit analyzer-start milestone (76-REQ-4.5)
            _emit("analyzer_start", pass_number=pass_number)
            try:
                cost, response = await session_runner(sys_prompt, task_prompt, "STANDARD")
                analyzer_cost = cost
                total_cost += cost
                sessions_consumed += 1
                max_session_cost = max(max_session_cost, cost)
                _emit("analyzer_done", pass_number=pass_number)
            except Exception:
                logger.error("Analyzer session failed", exc_info=True)
                termination_reason = ImproveTermination.ANALYZER_ERROR
                break

            # Parse analyzer response
            try:
                analyzer_result = parse_analyzer_response(response)
            except ValueError:
                logger.warning("Analyzer response was not valid JSON; treating as zero improvements")
                termination_reason = ImproveTermination.CONVERGED
                _emit("converged", pass_number=pass_number)
                break

            # Check diminishing returns (31-REQ-8.1)
            if analyzer_result.diminishing_returns:
                termination_reason = ImproveTermination.CONVERGED
                _emit("converged", pass_number=pass_number)
                break

            # Filter improvements (31-REQ-3.4, 31-REQ-3.5)
            actionable = filter_improvements(analyzer_result.improvements)
            if not actionable:
                termination_reason = ImproveTermination.CONVERGED
                _emit("converged", pass_number=pass_number)
                break

            # -- Coder (31-REQ-5.*) --
            # Check budget before coder session (31-REQ-8.3)
            if remaining_budget is not None and (remaining_budget - total_cost < max_session_cost):
                termination_reason = ImproveTermination.COST_LIMIT
                break

            coder_sys, coder_task = _build_coder_prompt(actionable)

            # Emit coder-start milestone (76-REQ-4.6)
            _emit("coder_start", pass_number=pass_number)
            try:
                cost, _coder_response = await session_runner(coder_sys, coder_task, "ADVANCED")
                coder_cost = cost
                total_cost += cost
                sessions_consumed += 1
                max_session_cost = max(max_session_cost, cost)
                _emit("coder_done", pass_number=pass_number)
            except Exception:
                logger.error("Coder session failed", exc_info=True)
                discard_partial_changes(project_root)
                termination_reason = ImproveTermination.CODER_ERROR
                break

            # Create git commit (31-REQ-5.4)
            _create_commit(project_root, pass_number, analyzer_result.summary)

            # -- Verifier (31-REQ-6.*) --
            # Check budget before verifier session (31-REQ-8.3)
            if remaining_budget is not None and (remaining_budget - total_cost < max_session_cost):
                termination_reason = ImproveTermination.COST_LIMIT
                break

            verifier_sys, verifier_task = _build_verifier_prompt(pass_number)

            # Emit verifier-start milestone (76-REQ-4.6)
            _emit("verifier_start", pass_number=pass_number)
            try:
                cost, verifier_response = await session_runner(verifier_sys, verifier_task, "STANDARD")
                verifier_cost = cost
                total_cost += cost
                sessions_consumed += 1
                max_session_cost = max(max_session_cost, cost)
            except Exception:
                # Session failure treated as FAIL (31-REQ-6.E1)
                logger.error("Verifier session failed", exc_info=True)
                verifier_response = ""

            # Parse verdict
            try:
                verdict = parse_verifier_verdict(verifier_response)
                verdict_str = verdict.verdict
                evidence = verdict.evidence
            except ValueError:
                # Invalid JSON treated as FAIL (31-REQ-6.E2)
                verdict_str = "FAIL"
                evidence = "Verifier response was not valid JSON"

            # Tier counts for this pass
            pass_tiers: Counter[str] = Counter()
            for imp in actionable:
                pass_tiers[imp.tier] += 1

            rolled_back = False

            if verdict_str == "PASS":
                verifier_pass_count += 1
                total_improvements += len(actionable)
                all_tiers.update(pass_tiers)
                previous_pass_summary = f"Pass {pass_number}: Applied {len(actionable)} improvements. Verifier: PASS."
                _emit("verifier_pass", pass_number=pass_number)
            else:
                # FAIL: rollback (31-REQ-7.1, 31-REQ-7.2)
                verifier_fail_count += 1
                rolled_back = True
                logger.info(
                    "Verifier FAIL on pass %d: %s. Rolling back.",
                    pass_number,
                    evidence,
                )
                rollback_improvement_pass(project_root)
                termination_reason = ImproveTermination.VERIFIER_FAIL
                _emit("verifier_fail", detail=evidence, pass_number=pass_number)

            pass_results.append(
                ImprovePassResult(
                    pass_number=pass_number,
                    improvements_applied=len(actionable),
                    improvements_by_tier=dict(pass_tiers),
                    verifier_verdict=verdict_str,
                    analyzer_cost=analyzer_cost,
                    coder_cost=coder_cost,
                    verifier_cost=verifier_cost,
                    rolled_back=rolled_back,
                )
            )

            if rolled_back:
                # Terminate after rollback (31-REQ-7.2)
                break

        except KeyboardInterrupt:
            termination_reason = ImproveTermination.INTERRUPTED
            break
    else:
        # Loop completed all passes without break
        termination_reason = ImproveTermination.PASS_LIMIT

    return ImproveResult(
        passes_completed=len(pass_results),
        max_passes=max_passes,
        total_improvements=total_improvements,
        improvements_by_tier=dict(all_tiers),
        verifier_pass_count=verifier_pass_count,
        verifier_fail_count=verifier_fail_count,
        sessions_consumed=sessions_consumed,
        total_cost=total_cost,
        termination_reason=termination_reason,
        pass_results=pass_results,
    )
