"""Unit tests for the converge_reviewer() dispatch function.

Covers:
- Pre-review routes to skeptic convergence (TS-98-11)
- Drift-review routes to skeptic convergence (TS-98-11)
- Audit-review routes to auditor convergence (TS-98-12)
- Unknown mode raises ValueError (TS-98-E4)

Test Spec: TS-98-11, TS-98-12, TS-98-E4
Requirements: 98-REQ-5.1, 98-REQ-5.2, 98-REQ-5.3, 98-REQ-5.E1
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_findings(n: int, severity: str = "critical", description: str = "Issue") -> list:
    """Build a list of Finding objects."""
    from agent_fox.session.convergence import Finding

    return [Finding(severity=severity, description=f"{description} {i}") for i in range(n)]


def _make_audit_result(verdict: str = "PASS"):
    """Build a minimal AuditResult."""
    from agent_fox.session.convergence import AuditEntry, AuditResult

    entry = AuditEntry(
        ts_entry="TS-1",
        test_functions=["test_foo"],
        verdict=verdict,
        notes=None,
    )
    return AuditResult(
        entries=[entry],
        overall_verdict=verdict,
        summary="ok" if verdict == "PASS" else "failed",
    )


# ---------------------------------------------------------------------------
# TS-98-11: Convergence Dispatch Pre-review and Drift-review
# Requirements: 98-REQ-5.1, 98-REQ-5.2
# ---------------------------------------------------------------------------


class TestConvergeReviewerPreReview:
    """Verify pre-review mode routes to skeptic convergence algorithm."""

    def test_pre_review_routes_to_skeptic(self) -> None:
        """TS-98-11: converge_reviewer(results, 'pre-review') uses skeptic algorithm."""
        from agent_fox.session.convergence import (
            converge_reviewer,  # type: ignore[attr-defined]
            converge_skeptic,
        )

        # 3 instances, each with 1 critical finding (same description for dedup)
        results = [
            [_make_findings(1, "critical", "Critical bug")[0]],
            [_make_findings(1, "critical", "Critical bug")[0]],
            [_make_findings(1, "major", "Major issue")[0]],
        ]

        result = converge_reviewer(results, mode="pre-review", block_threshold=3)
        expected = converge_skeptic(results, block_threshold=3)

        assert result == expected, (
            f"pre-review convergence should match converge_skeptic output. "
            f"Expected {expected}, got {result}"
        )

    def test_pre_review_blocking(self) -> None:
        """TS-98-11: pre-review convergence applies majority-gated blocking."""
        from agent_fox.session.convergence import converge_reviewer  # type: ignore[attr-defined]

        # 3 instances, each with the same critical finding — majority agrees
        critical_finding = _make_findings(1, "critical", "Critical X")[0]
        results = [
            [critical_finding],
            [critical_finding],
            [critical_finding],
        ]
        # block_threshold=0 means any critical blocks
        _, blocked = converge_reviewer(results, mode="pre-review", block_threshold=0)
        assert blocked is True, (
            "pre-review should block when majority agree on critical finding "
            "and block_threshold=0"
        )

    def test_drift_review_routes_to_skeptic(self) -> None:
        """TS-98-11: converge_reviewer(results, 'drift-review') uses skeptic algorithm."""
        from agent_fox.session.convergence import (
            converge_reviewer,  # type: ignore[attr-defined]
            converge_skeptic,
        )

        results = [
            [_make_findings(1, "major", "Drift issue")[0]],
            [_make_findings(1, "minor", "Small drift")[0]],
        ]

        result = converge_reviewer(results, mode="drift-review", block_threshold=5)
        expected = converge_skeptic(results, block_threshold=5)

        assert result == expected, (
            f"drift-review convergence should match converge_skeptic output. "
            f"Expected {expected}, got {result}"
        )


# ---------------------------------------------------------------------------
# TS-98-12: Convergence Dispatch Audit-review
# Requirement: 98-REQ-5.3
# ---------------------------------------------------------------------------


class TestConvergeReviewerAuditReview:
    """Verify audit-review mode routes to auditor convergence algorithm."""

    def test_audit_review_routes_to_auditor(self) -> None:
        """TS-98-12: converge_reviewer(results, 'audit-review') uses auditor algorithm."""
        from agent_fox.session.convergence import (
            AuditResult,
            converge_auditor,
            converge_reviewer,  # type: ignore[attr-defined]
        )

        audit_results = [
            _make_audit_result("PASS"),
            _make_audit_result("FAIL"),
        ]

        result = converge_reviewer(audit_results, mode="audit-review")
        expected = converge_auditor(audit_results)

        # Both should produce an AuditResult
        assert isinstance(result, AuditResult), (
            f"audit-review convergence should return AuditResult, got {type(result)}"
        )
        assert result.overall_verdict == expected.overall_verdict, (
            f"audit-review verdict should match converge_auditor. "
            f"Expected {expected.overall_verdict}, got {result.overall_verdict}"
        )

    def test_audit_review_fail_propagates(self) -> None:
        """TS-98-12: audit-review convergence propagates FAIL verdict."""
        from agent_fox.session.convergence import converge_reviewer  # type: ignore[attr-defined]

        audit_results = [
            _make_audit_result("FAIL"),
        ]
        result = converge_reviewer(audit_results, mode="audit-review")
        assert result.overall_verdict == "FAIL", (
            f"audit-review should propagate FAIL, got {result.overall_verdict}"
        )


# ---------------------------------------------------------------------------
# TS-98-E4: Unknown Convergence Mode
# Requirement: 98-REQ-5.E1
# ---------------------------------------------------------------------------


class TestConvergeReviewerUnknownMode:
    """Verify unknown mode raises ValueError."""

    def test_unknown_mode(self) -> None:
        """TS-98-E4: converge_reviewer with unknown mode raises ValueError."""
        from agent_fox.session.convergence import converge_reviewer  # type: ignore[attr-defined]

        with pytest.raises(ValueError, match="[Uu]nknown"):
            converge_reviewer([], mode="unknown-mode")

    def test_empty_string_mode(self) -> None:
        """TS-98-E4: converge_reviewer with empty string mode raises ValueError."""
        from agent_fox.session.convergence import converge_reviewer  # type: ignore[attr-defined]

        with pytest.raises(ValueError):
            converge_reviewer([], mode="")

    def test_none_mode_raises(self) -> None:
        """TS-98-E4: converge_reviewer with None mode raises ValueError."""
        from agent_fox.session.convergence import converge_reviewer  # type: ignore[attr-defined]

        with pytest.raises((ValueError, TypeError)):
            converge_reviewer([], mode=None)  # type: ignore[arg-type]
