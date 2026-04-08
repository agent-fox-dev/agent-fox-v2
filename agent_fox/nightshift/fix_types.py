"""Data types for the fix pipeline triage and review workflow.

Requirements: 82-REQ-2.1, 82-REQ-2.2, 82-REQ-2.3, 82-REQ-5.1
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AcceptanceCriterion:
    """A single acceptance criterion from the triage agent.

    Requirements: 82-REQ-2.2
    """

    id: str  # e.g. "AC-1"
    description: str
    preconditions: str
    expected: str
    assertion: str


@dataclass(frozen=True)
class TriageResult:
    """Parsed triage output.

    Requirements: 82-REQ-2.1, 82-REQ-2.3
    """

    summary: str = ""
    affected_files: list[str] = field(default_factory=list)
    criteria: list[AcceptanceCriterion] = field(default_factory=list)


@dataclass(frozen=True)
class FixReviewVerdict:
    """A single per-criterion verdict from the fix reviewer.

    Requirements: 82-REQ-5.1
    """

    criterion_id: str  # matches AcceptanceCriterion.id
    verdict: str  # "PASS" or "FAIL"
    evidence: str


@dataclass(frozen=True)
class FixReviewResult:
    """Parsed fix reviewer output.

    Requirements: 82-REQ-5.1
    """

    verdicts: list[FixReviewVerdict] = field(default_factory=list)
    overall_verdict: str = "FAIL"  # "PASS" or "FAIL"
    summary: str = ""
    is_parse_failure: bool = False
