"""Multi-instance convergence logic for archetype sessions.

Provides deterministic post-processing for multi-instance archetype runs:
- Skeptic: union findings, normalize-dedup, majority-gate criticals,
  apply blocking threshold.
- Verifier: majority vote on verdicts.

No LLM calls. Pure string manipulation and counting.

Requirements: 26-REQ-7.2, 26-REQ-7.3, 26-REQ-7.4, 26-REQ-7.5, 26-REQ-7.E1,
              27-REQ-6.1, 27-REQ-6.2, 27-REQ-6.3, 27-REQ-6.E1
"""

from __future__ import annotations

import math
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_fox.knowledge.review_store import ReviewFinding, VerificationResult


@dataclass(frozen=True)
class Finding:
    """A single review finding with severity and description."""

    severity: str  # "critical" | "major" | "minor" | "observation"
    description: str


def normalize_finding(f: Finding) -> tuple[str, str]:
    """Normalize for dedup: lowercase, collapse whitespace.

    Returns a (severity, description) tuple suitable for set-based dedup.
    """
    return (
        f.severity.lower().strip(),
        " ".join(f.description.lower().split()),
    )


def converge_skeptic(
    instance_findings: list[list[Finding]],
    block_threshold: int,
) -> tuple[list[Finding], bool]:
    """Union, dedup, majority-gate criticals. Returns (merged, blocked).

    1. Union all findings across instances.
    2. Deduplicate by normalized (severity, description).
    3. For each unique finding, count how many instances contain it.
    4. A critical finding counts toward blocking only if it appears
       in >= ceil(N/2) instances.
    5. blocked = (majority-agreed critical count > block_threshold).

    Requirements: 26-REQ-7.2, 26-REQ-7.3, 26-REQ-8.4
    """
    n_instances = len(instance_findings)
    if n_instances == 0:
        return [], False

    majority_threshold = math.ceil(n_instances / 2)

    # Count how many instances contain each normalized finding
    finding_instance_counts: Counter[tuple[str, str]] = Counter()
    # Keep a representative Finding for each normalized key
    representative: dict[tuple[str, str], Finding] = {}

    for instance in instance_findings:
        # Deduplicate within a single instance first
        seen_in_instance: set[tuple[str, str]] = set()
        for f in instance:
            key = normalize_finding(f)
            if key not in seen_in_instance:
                seen_in_instance.add(key)
                finding_instance_counts[key] += 1
                if key not in representative:
                    representative[key] = f

    # Build merged list: all unique findings (union)
    # Sort for determinism: by severity priority then description
    severity_order = {"critical": 0, "major": 1, "minor": 2, "observation": 3}
    merged = sorted(
        representative.values(),
        key=lambda f: (
            severity_order.get(f.severity.lower(), 99),
            normalize_finding(f)[1],
        ),
    )

    # Count majority-agreed critical findings
    majority_critical_count = 0
    for key, count in finding_instance_counts.items():
        severity = key[0]
        if severity == "critical" and count >= majority_threshold:
            majority_critical_count += 1

    blocked = majority_critical_count > block_threshold

    return merged, blocked


def converge_verifier(
    instance_verdicts: list[str],
) -> str:
    """Majority vote. Returns 'PASS' or 'FAIL'.

    PASS if >= ceil(N/2) instances report PASS.

    Requirements: 26-REQ-7.4
    """
    n = len(instance_verdicts)
    pass_count = sum(1 for v in instance_verdicts if v.upper() == "PASS")
    return "PASS" if pass_count >= math.ceil(n / 2) else "FAIL"


# ---------------------------------------------------------------------------
# DB-record-based convergence (spec 27)
# Requirements: 27-REQ-6.1, 27-REQ-6.2, 27-REQ-6.3, 27-REQ-6.E1
# ---------------------------------------------------------------------------


def converge_skeptic_records(
    instance_findings: list[list[ReviewFinding]],
    block_threshold: int,
) -> tuple[list[ReviewFinding], bool]:
    """Same algorithm as converge_skeptic but operating on ReviewFinding records.

    Returns (merged_findings, blocked).

    Requirements: 27-REQ-6.1, 27-REQ-6.3, 27-REQ-6.E1
    """
    from agent_fox.knowledge.review_store import ReviewFinding

    n_instances = len(instance_findings)
    if n_instances == 0:
        return [], False

    # 27-REQ-6.E1: Single instance — skip convergence
    if n_instances == 1:
        return list(instance_findings[0]), False

    majority_threshold = math.ceil(n_instances / 2)

    finding_instance_counts: Counter[tuple[str, str]] = Counter()
    representative: dict[tuple[str, str], ReviewFinding] = {}

    for instance in instance_findings:
        seen_in_instance: set[tuple[str, str]] = set()
        for f in instance:
            key = (
                f.severity.lower().strip(),
                " ".join(f.description.lower().split()),
            )
            if key not in seen_in_instance:
                seen_in_instance.add(key)
                finding_instance_counts[key] += 1
                if key not in representative:
                    representative[key] = f

    severity_order = {"critical": 0, "major": 1, "minor": 2, "observation": 3}
    merged = sorted(
        representative.values(),
        key=lambda f: (
            severity_order.get(f.severity.lower(), 99),
            " ".join(f.description.lower().split()),
        ),
    )

    # Assign new IDs to merged findings
    convergence_id = f"convergence-{uuid.uuid4()}"
    merged = [
        ReviewFinding(
            id=str(uuid.uuid4()),
            severity=f.severity,
            description=f.description,
            requirement_ref=f.requirement_ref,
            spec_name=f.spec_name,
            task_group=f.task_group,
            session_id=convergence_id,
            category=getattr(f, "category", None),
        )
        for f in merged
    ]

    majority_critical_count = 0
    for key, count in finding_instance_counts.items():
        severity = key[0]
        if severity == "critical" and count >= majority_threshold:
            majority_critical_count += 1

    blocked = majority_critical_count > block_threshold

    return merged, blocked


def converge_verifier_records(
    instance_verdicts: list[list[VerificationResult]],
) -> list[VerificationResult]:
    """Majority vote returning winning VerificationResult records.

    For each requirement_id, collects verdicts across instances and
    applies majority vote.

    Requirements: 27-REQ-6.2, 27-REQ-6.3, 27-REQ-6.E1
    """
    from agent_fox.knowledge.review_store import VerificationResult

    if not instance_verdicts:
        return []

    # 27-REQ-6.E1: Single instance — use records directly
    if len(instance_verdicts) == 1:
        return list(instance_verdicts[0])

    n_instances = len(instance_verdicts)
    majority_threshold = math.ceil(n_instances / 2)

    # Collect votes per requirement_id
    votes: dict[str, list[VerificationResult]] = {}
    for instance in instance_verdicts:
        for v in instance:
            votes.setdefault(v.requirement_id, []).append(v)

    convergence_id = f"convergence-{uuid.uuid4()}"
    merged: list[VerificationResult] = []

    for req_id, req_verdicts in sorted(votes.items()):
        pass_count = sum(1 for v in req_verdicts if v.verdict == "PASS")
        winning_verdict = "PASS" if pass_count >= majority_threshold else "FAIL"

        # Use the first matching verdict as representative for evidence
        representative = next(
            (v for v in req_verdicts if v.verdict == winning_verdict),
            req_verdicts[0],
        )

        merged.append(
            VerificationResult(
                id=str(uuid.uuid4()),
                requirement_id=req_id,
                verdict=winning_verdict,
                evidence=representative.evidence,
                spec_name=representative.spec_name,
                task_group=representative.task_group,
                session_id=convergence_id,
            )
        )

    return merged


# ---------------------------------------------------------------------------
# Learned blocking threshold integration (spec 39)
# Requirements: 39-REQ-10.2, 39-REQ-10.3
# ---------------------------------------------------------------------------


def resolve_block_threshold(
    configured_threshold: int,
    archetype: str,
    conn: Any = None,
    *,
    learn_thresholds: bool = False,
) -> int:
    """Resolve the effective blocking threshold.

    When learned thresholds are enabled and available, uses the learned
    threshold instead of the configured one. Falls back to the configured
    threshold when learning is disabled or insufficient data exists.

    Args:
        configured_threshold: The statically configured threshold.
        archetype: The archetype type ("skeptic" or "oracle").
        conn: Optional DuckDB connection for querying learned thresholds.
        learn_thresholds: Whether threshold learning is enabled.

    Returns:
        The effective blocking threshold to use.

    Requirements: 39-REQ-10.2, 39-REQ-10.3
    """
    if not learn_thresholds or conn is None:
        return configured_threshold

    try:
        from agent_fox.knowledge.blocking_history import get_learned_threshold

        learned = get_learned_threshold(conn, archetype)
        if learned is not None:
            return learned
    except Exception:
        pass

    return configured_threshold


# ---------------------------------------------------------------------------
# Auditor convergence (spec 46)
# Requirements: 46-REQ-6.1, 46-REQ-6.2, 46-REQ-6.3, 46-REQ-6.4,
#               46-REQ-6.E1, 46-REQ-6.E2
# ---------------------------------------------------------------------------

# Verdict severity order: MISSING > MISALIGNED > WEAK > PASS
_VERDICT_SEVERITY: dict[str, int] = {
    "PASS": 0,
    "WEAK": 1,
    "MISALIGNED": 2,
    "MISSING": 3,
}


@dataclass(frozen=True)
class AuditEntry:
    """A single TS entry audit result."""

    ts_entry: str
    test_functions: list[str]
    verdict: str  # PASS | WEAK | MISSING | MISALIGNED
    notes: str | None = None


@dataclass(frozen=True)
class AuditResult:
    """Aggregated audit result for a spec."""

    entries: list[AuditEntry]
    overall_verdict: str  # PASS | FAIL
    summary: str


def converge_auditor(
    instance_results: list[AuditResult],
) -> AuditResult:
    """Merge multiple auditor instance results using union semantics.

    A TS entry takes the worst verdict across instances.
    Overall verdict is FAIL if any instance verdict is FAIL.

    Requirements: 46-REQ-6.1, 46-REQ-6.2, 46-REQ-6.3, 46-REQ-6.4,
                  46-REQ-6.E1, 46-REQ-6.E2
    """
    import logging as _logging

    _logger = _logging.getLogger(__name__)

    # 46-REQ-6.E2: Empty list returns PASS with warning
    if not instance_results:
        _logger.warning("No auditor instance results; treating as PASS")
        return AuditResult(entries=[], overall_verdict="PASS", summary="No results")

    # 46-REQ-6.E1: Single instance passthrough
    if len(instance_results) == 1:
        return instance_results[0]

    # 46-REQ-6.1: Union semantics — worst verdict per TS entry wins
    entry_map: dict[str, AuditEntry] = {}
    for result in instance_results:
        for entry in result.entries:
            existing = entry_map.get(entry.ts_entry)
            if existing is None:
                entry_map[entry.ts_entry] = entry
            else:
                existing_sev = _VERDICT_SEVERITY.get(existing.verdict, 0)
                new_sev = _VERDICT_SEVERITY.get(entry.verdict, 0)
                if new_sev > existing_sev:
                    merged_funcs = list(dict.fromkeys(existing.test_functions + entry.test_functions))
                    entry_map[entry.ts_entry] = AuditEntry(
                        ts_entry=entry.ts_entry,
                        test_functions=merged_funcs,
                        verdict=entry.verdict,
                        notes=entry.notes or existing.notes,
                    )

    merged_entries = sorted(entry_map.values(), key=lambda e: e.ts_entry)

    # 46-REQ-6.3: Overall FAIL if any instance FAILs
    overall = "FAIL" if any(r.overall_verdict == "FAIL" for r in instance_results) else "PASS"

    summaries = [r.summary for r in instance_results if r.summary]
    merged_summary = "; ".join(summaries) if summaries else ""

    return AuditResult(
        entries=merged_entries,
        overall_verdict=overall,
        summary=merged_summary,
    )


# ---------------------------------------------------------------------------
# Reviewer convergence dispatch (spec 98)
# Requirements: 98-REQ-5.1, 98-REQ-5.2, 98-REQ-5.3, 98-REQ-5.E1
# ---------------------------------------------------------------------------


def converge_reviewer(
    results: list,
    mode: str,
    *,
    block_threshold: int = 3,
) -> Any:
    """Dispatch convergence to the correct algorithm by reviewer mode.

    Routing:
    - ``"pre-review"`` and ``"drift-review"`` → :func:`converge_skeptic`
      (majority-gated blocking on ``list[list[Finding]]`` results)
    - ``"audit-review"`` → :func:`converge_auditor`
      (union / worst-verdict-wins on ``list[AuditResult]`` results)
    - ``"fix-review"`` → single-instance passthrough (raises if multiple)
    - Any other mode → :exc:`ValueError`

    Args:
        results: Instance results.  Type depends on mode:
            - pre-review / drift-review: ``list[list[Finding]]``
            - audit-review: ``list[AuditResult]``
            - fix-review: single-element ``list``
        mode: Reviewer mode string (``"pre-review"``, ``"drift-review"``,
            ``"audit-review"``, or ``"fix-review"``).
        block_threshold: Passed to :func:`converge_skeptic` for pre/drift modes.

    Returns:
        - For pre-review / drift-review: ``tuple[list[Finding], bool]``
        - For audit-review: :class:`AuditResult`
        - For fix-review: the single element in *results*

    Raises:
        ValueError: If *mode* is unknown or None.

    Requirements: 98-REQ-5.1, 98-REQ-5.2, 98-REQ-5.3, 98-REQ-5.E1
    """
    if mode in ("pre-review", "drift-review"):
        return converge_skeptic(results, block_threshold=block_threshold)
    elif mode == "audit-review":
        return converge_auditor(results)
    elif mode == "fix-review":
        if len(results) != 1:
            raise ValueError(
                f"fix-review mode does not support multi-instance convergence; expected 1 result, got {len(results)}"
            )
        return results[0]
    else:
        raise ValueError(
            f"Unknown reviewer mode: {mode!r}. "
            f"Valid modes are: 'pre-review', 'drift-review', 'audit-review', 'fix-review'."
        )
