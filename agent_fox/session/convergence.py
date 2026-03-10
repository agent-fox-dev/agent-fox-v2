"""Multi-instance convergence logic for archetype sessions.

Provides deterministic post-processing for multi-instance archetype runs:
- Skeptic: union findings, normalize-dedup, majority-gate criticals,
  apply blocking threshold.
- Verifier: majority vote on verdicts.

No LLM calls. Pure string manipulation and counting.

Requirements: 26-REQ-7.2, 26-REQ-7.3, 26-REQ-7.4, 26-REQ-7.5, 26-REQ-7.E1
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass


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
