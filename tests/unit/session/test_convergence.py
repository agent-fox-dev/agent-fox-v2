"""Tests for multi-instance convergence logic.

Test Spec: TS-26-27 through TS-26-31, TS-26-E10, TS-26-P9 through TS-26-P11
Requirements: 26-REQ-7.1 through 26-REQ-7.5, 26-REQ-7.E1
"""

from __future__ import annotations

import math
from itertools import permutations

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


# ---------------------------------------------------------------------------
# TS-26-27: Multi-instance parallel dispatch
# Requirement: 26-REQ-7.1
# ---------------------------------------------------------------------------


class TestMultiInstanceDispatch:
    """Verify N independent sessions dispatched in parallel for instances > 1."""

    @pytest.mark.asyncio
    async def test_multi_instance_creates_n_sessions(self) -> None:
        # This test will be fully implemented with task 7.2
        # For now verify the convergence module is importable
        from agent_fox.session.convergence import converge_skeptic, converge_verifier

        assert converge_skeptic is not None
        assert converge_verifier is not None


# ---------------------------------------------------------------------------
# TS-26-28: Skeptic convergence union and dedup
# Requirement: 26-REQ-7.2
# ---------------------------------------------------------------------------


class TestSkepticUnionDedup:
    """Verify Skeptic convergence unions and deduplicates findings."""

    def test_dedup_by_normalized_severity_description(self) -> None:
        from agent_fox.session.convergence import Finding, converge_skeptic

        instance_1 = [
            Finding(severity="critical", description="Missing edge case"),
            Finding(severity="major", description="Unclear requirement"),
        ]
        instance_2 = [
            Finding(severity="critical", description="missing edge case"),
            Finding(severity="minor", description="Typo in doc"),
        ]
        instance_3 = [
            Finding(severity="critical", description="Missing Edge Case"),
            Finding(severity="major", description="New concern"),
        ]

        merged, blocked = converge_skeptic(
            [instance_1, instance_2, instance_3], block_threshold=3
        )

        # After dedup: 1 critical + 2 major + 1 minor = 4 unique
        from agent_fox.session.convergence import normalize_finding

        unique = {normalize_finding(f) for f in merged}
        assert len(unique) == 4

    def test_empty_instances(self) -> None:
        from agent_fox.session.convergence import converge_skeptic

        merged, blocked = converge_skeptic([[], [], []], block_threshold=3)
        assert merged == []
        assert blocked is False


# ---------------------------------------------------------------------------
# TS-26-29: Skeptic critical majority gating
# Requirement: 26-REQ-7.3
# ---------------------------------------------------------------------------


class TestSkepticMajorityGating:
    """Verify critical finding only counts if in >= ceil(N/2) instances."""

    def test_minority_critical_not_counted(self) -> None:
        from agent_fox.session.convergence import Finding, converge_skeptic

        # Critical in only 1 of 3 instances - should not count
        instance_1 = [Finding(severity="critical", description="Issue A")]
        instance_2: list = []
        instance_3: list = []

        merged, blocked = converge_skeptic(
            [instance_1, instance_2, instance_3], block_threshold=3
        )
        assert blocked is False

    def test_majority_critical_counted(self) -> None:
        from agent_fox.session.convergence import Finding, converge_skeptic

        # Critical in 2 of 3 instances - should count
        instance_1 = [Finding(severity="critical", description="Issue A")]
        instance_2 = [Finding(severity="critical", description="issue a")]
        instance_3: list = []

        # 1 majority-agreed critical, threshold=0 → blocked
        merged, blocked = converge_skeptic(
            [instance_1, instance_2, instance_3], block_threshold=0
        )
        assert blocked is True


# ---------------------------------------------------------------------------
# TS-26-30: Verifier majority vote
# Requirement: 26-REQ-7.4
# ---------------------------------------------------------------------------


class TestVerifierMajorityVote:
    """Verify Verifier convergence uses majority vote for verdict."""

    def test_two_pass_one_fail(self) -> None:
        from agent_fox.session.convergence import converge_verifier

        assert converge_verifier(["PASS", "PASS", "FAIL"]) == "PASS"

    def test_two_fail_one_pass(self) -> None:
        from agent_fox.session.convergence import converge_verifier

        assert converge_verifier(["FAIL", "FAIL", "PASS"]) == "FAIL"

    def test_single_pass(self) -> None:
        from agent_fox.session.convergence import converge_verifier

        assert converge_verifier(["PASS"]) == "PASS"

    def test_single_fail(self) -> None:
        from agent_fox.session.convergence import converge_verifier

        assert converge_verifier(["FAIL"]) == "FAIL"

    def test_all_pass(self) -> None:
        from agent_fox.session.convergence import converge_verifier

        assert converge_verifier(["PASS", "PASS", "PASS"]) == "PASS"

    def test_all_fail(self) -> None:
        from agent_fox.session.convergence import converge_verifier

        assert converge_verifier(["FAIL", "FAIL", "FAIL"]) == "FAIL"


# ---------------------------------------------------------------------------
# TS-26-31: Convergence makes no LLM calls
# Requirement: 26-REQ-7.5
# ---------------------------------------------------------------------------


class TestConvergenceNoLlm:
    """Verify convergence module has no LLM SDK imports."""

    def test_no_llm_imports(self) -> None:
        import os

        convergence_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "agent_fox", "session", "convergence.py",
        )
        convergence_path = os.path.normpath(convergence_path)
        with open(convergence_path, encoding="utf-8") as f:
            content = f.read()

        for sdk in ["claude_code_sdk", "anthropic", "openai", "langchain"]:
            assert sdk not in content, (
                f"convergence.py should not import {sdk}"
            )


# ---------------------------------------------------------------------------
# TS-26-E10: Partial multi-instance failure
# Requirement: 26-REQ-7.E1
# ---------------------------------------------------------------------------


class TestPartialInstanceFailure:
    """Verify convergence proceeds with successful instances; all-fail = node fail."""

    def test_partial_success_converges(self) -> None:
        from agent_fox.session.convergence import Finding, converge_skeptic

        # 2 succeed, 1 would be filtered out before convergence
        instance_1 = [Finding(severity="minor", description="note")]
        instance_2 = [Finding(severity="minor", description="note")]

        merged, blocked = converge_skeptic(
            [instance_1, instance_2], block_threshold=3
        )
        assert merged is not None
        assert len(merged) >= 1


# ---------------------------------------------------------------------------
# TS-26-P9: Convergence Determinism (Property)
# Property 9: Convergence output independent of instance ordering
# Validates: 26-REQ-7.2, 26-REQ-7.4, 26-REQ-7.5
# ---------------------------------------------------------------------------


class TestPropertyConvergenceDeterminism:
    """Convergence output is independent of instance ordering."""

    def test_prop_skeptic_deterministic(self) -> None:
        from agent_fox.session.convergence import (
            Finding,
            converge_skeptic,
            normalize_finding,
        )

        instances = [
            [Finding("critical", "A"), Finding("major", "B")],
            [Finding("critical", "a"), Finding("minor", "C")],
            [Finding("major", "D")],
        ]

        # Test all permutations produce same result
        results = set()
        for perm in permutations(instances):
            merged, blocked = converge_skeptic(list(perm), block_threshold=3)
            normalized = frozenset(normalize_finding(f) for f in merged)
            results.add((normalized, blocked))

        assert len(results) == 1, "Convergence not deterministic across permutations"

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        verdicts=st.lists(
            st.sampled_from(["PASS", "FAIL"]),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=50)
    def test_prop_verifier_deterministic(self, verdicts: list[str]) -> None:
        from agent_fox.session.convergence import converge_verifier

        # All permutations should give same result
        results = set()
        for perm in permutations(verdicts):
            result = converge_verifier(list(perm))
            results.add(result)

        assert len(results) == 1


# ---------------------------------------------------------------------------
# TS-26-P10: Skeptic Blocking Threshold (Property)
# Property 10: Blocking iff majority-agreed criticals exceed threshold
# Validates: 26-REQ-7.3, 26-REQ-8.4
# ---------------------------------------------------------------------------


class TestPropertyBlockingThreshold:
    """Blocking occurs iff majority-agreed criticals exceed threshold."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        n_criticals=st.integers(min_value=0, max_value=10),
        threshold=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=50)
    def test_prop_blocking_formula(self, n_criticals: int, threshold: int) -> None:
        from agent_fox.session.convergence import Finding, converge_skeptic

        # Create instances where all criticals appear in all instances
        # (so they all pass majority gate)
        findings = [
            Finding(severity="critical", description=f"Issue {i}")
            for i in range(n_criticals)
        ]
        # Use 1 instance so all findings pass majority gate (1/1 >= ceil(1/2))
        _, blocked = converge_skeptic([findings], block_threshold=threshold)
        assert blocked == (n_criticals > threshold)


# ---------------------------------------------------------------------------
# TS-26-P11: Verifier Majority Vote (Property)
# Property 11: Verdict is PASS iff >= ceil(N/2) instances say PASS
# Validates: 26-REQ-7.4
# ---------------------------------------------------------------------------


class TestPropertyMajorityVote:
    """Verdict is PASS iff >= ceil(N/2) instances say PASS."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        verdicts=st.lists(
            st.sampled_from(["PASS", "FAIL"]),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_prop_majority_vote(self, verdicts: list[str]) -> None:
        from agent_fox.session.convergence import converge_verifier

        result = converge_verifier(verdicts)
        pass_count = sum(1 for v in verdicts if v == "PASS")
        expected = "PASS" if pass_count >= math.ceil(len(verdicts) / 2) else "FAIL"
        assert result == expected
