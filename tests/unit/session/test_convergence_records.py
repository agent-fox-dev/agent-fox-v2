"""Unit tests for DB-record-based convergence.

Test Spec: TS-27-12, TS-27-13
Requirements: 27-REQ-6.1, 27-REQ-6.2, 27-REQ-6.3, 27-REQ-6.E1
"""

from __future__ import annotations

import uuid

from agent_fox.knowledge.review_store import ReviewFinding, VerificationResult
from agent_fox.session.convergence import (
    converge_skeptic_records,
    converge_verifier_records,
)


def _make_finding(
    severity: str = "major",
    description: str = "Test finding",
    spec_name: str = "test_spec",
    session_id: str = "s1",
) -> ReviewFinding:
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group="1",
        session_id=session_id,
    )


def _make_verdict(
    requirement_id: str = "05-REQ-1.1",
    verdict: str = "PASS",
    evidence: str | None = "Tests pass",
    spec_name: str = "test_spec",
    session_id: str = "s1",
) -> VerificationResult:
    return VerificationResult(
        id=str(uuid.uuid4()),
        requirement_id=requirement_id,
        verdict=verdict,
        evidence=evidence,
        spec_name=spec_name,
        task_group="1",
        session_id=session_id,
    )


class TestConvergeSkepticRecords:
    """TS-27-12: converge skeptic records from multiple instances."""

    def test_converge_skeptic_records(self) -> None:
        """Union-dedup-majority-gate on ReviewFinding records."""
        instance_1 = [
            _make_finding(severity="critical", description="Issue A", session_id="s1"),
            _make_finding(severity="major", description="Issue B", session_id="s1"),
        ]
        instance_2 = [
            _make_finding(severity="critical", description="Issue A", session_id="s2"),
            _make_finding(severity="minor", description="Issue C", session_id="s2"),
        ]

        merged, blocked = converge_skeptic_records([instance_1, instance_2], block_threshold=0)

        descriptions = [f.description for f in merged]
        assert "Issue A" in descriptions
        assert "Issue B" in descriptions
        assert "Issue C" in descriptions

        # Issue A is critical and majority-agreed (2/2) -> blocked
        assert blocked is True

    def test_non_majority_critical_not_blocking(self) -> None:
        """Critical finding in minority does not cause blocking."""
        instance_1 = [
            _make_finding(severity="critical", description="Only in one", session_id="s1"),
        ]
        instance_2 = [
            _make_finding(severity="minor", description="Minor thing", session_id="s2"),
        ]
        instance_3 = [
            _make_finding(severity="minor", description="Another minor", session_id="s3"),
        ]

        merged, blocked = converge_skeptic_records([instance_1, instance_2, instance_3], block_threshold=0)

        assert blocked is False

    def test_convergence_writes_back(self) -> None:
        """Merged findings have a convergence session_id."""
        instance_1 = [_make_finding(session_id="s1")]
        merged, _ = converge_skeptic_records([instance_1, instance_1], block_threshold=5)
        for f in merged:
            assert f.session_id.startswith("convergence-")


class TestConvergeVerifierRecords:
    """TS-27-13: converge verifier records from multiple instances."""

    def test_converge_verifier_records(self) -> None:
        """Majority vote on VerificationResult records."""
        instance_1 = [
            _make_verdict(requirement_id="REQ-1", verdict="PASS", session_id="s1"),
            _make_verdict(requirement_id="REQ-2", verdict="FAIL", session_id="s1"),
        ]
        instance_2 = [
            _make_verdict(requirement_id="REQ-1", verdict="PASS", session_id="s2"),
            _make_verdict(requirement_id="REQ-2", verdict="PASS", session_id="s2"),
        ]
        instance_3 = [
            _make_verdict(requirement_id="REQ-1", verdict="FAIL", session_id="s3"),
            _make_verdict(requirement_id="REQ-2", verdict="PASS", session_id="s3"),
        ]

        merged = converge_verifier_records([instance_1, instance_2, instance_3])

        result_map = {v.requirement_id: v.verdict for v in merged}
        assert result_map["REQ-1"] == "PASS"  # 2/3 PASS
        assert result_map["REQ-2"] == "PASS"  # 2/3 PASS

    def test_convergence_writes_back_verdicts(self) -> None:
        """Merged verdicts have a convergence session_id."""
        instance_1 = [_make_verdict(session_id="s1")]
        instance_2 = [_make_verdict(session_id="s2")]
        merged = converge_verifier_records([instance_1, instance_2])
        for v in merged:
            assert v.session_id.startswith("convergence-")


class TestSingleInstanceSkips:
    """TS-27-E8: single instance skips convergence."""

    def test_single_instance_skips_skeptic(self) -> None:
        """Single instance returns findings directly."""
        findings = [_make_finding(description="Only finding")]
        merged, blocked = converge_skeptic_records([findings], block_threshold=0)
        assert len(merged) == 1
        assert merged[0].description == "Only finding"
        assert blocked is False

    def test_single_instance_skips_verifier(self) -> None:
        """Single instance returns verdicts directly."""
        verdicts = [_make_verdict()]
        merged = converge_verifier_records([verdicts])
        assert len(merged) == 1

    def test_empty_instances_skeptic(self) -> None:
        """Empty instance list returns empty result."""
        merged, blocked = converge_skeptic_records([], block_threshold=0)
        assert merged == []
        assert blocked is False

    def test_empty_instances_verifier(self) -> None:
        """Empty instance list returns empty result."""
        merged = converge_verifier_records([])
        assert merged == []
