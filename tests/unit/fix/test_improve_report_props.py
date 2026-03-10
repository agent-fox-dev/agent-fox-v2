"""Improve report property tests.

Test Spec: TS-31-P5 (report field consistency)
Property: Property 7 from design.md
Requirements: 31-REQ-9.1
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.fix.improve import ImproveResult, ImproveTermination

TERMINATION_REASONS = list(ImproveTermination)


def improve_result_strategy() -> st.SearchStrategy[ImproveResult]:
    """Generate valid ImproveResult objects."""
    return st.builds(
        _build_consistent_result,
        max_passes=st.integers(min_value=1, max_value=10),
        passes_completed=st.integers(min_value=0, max_value=10),
        termination_reason=st.sampled_from(TERMINATION_REASONS),
    )


def _build_consistent_result(
    max_passes: int,
    passes_completed: int,
    termination_reason: ImproveTermination,
) -> ImproveResult:
    """Build a consistent ImproveResult (passes_completed <= max_passes)."""
    passes_completed = min(passes_completed, max_passes)
    # Distribute verdicts across passes; ensure fail_count <= passes_completed
    fail_count = (
        1
        if termination_reason == ImproveTermination.VERIFIER_FAIL
        and passes_completed > 0
        else 0
    )
    pass_count = max(0, passes_completed - fail_count)

    return ImproveResult(
        passes_completed=passes_completed,
        max_passes=max_passes,
        total_improvements=pass_count * 2,
        improvements_by_tier={"quick_win": pass_count},
        verifier_pass_count=pass_count,
        verifier_fail_count=fail_count,
        sessions_consumed=passes_completed * 3,
        total_cost=passes_completed * 0.30,
        termination_reason=termination_reason,
        pass_results=[],
    )


class TestReportFieldConsistency:
    """TS-31-P5: ImproveResult fields are internally consistent."""

    @given(result=improve_result_strategy())
    @settings(max_examples=50)
    def test_fields_consistent(self, result: ImproveResult) -> None:
        assert result.passes_completed <= result.max_passes
        assert (
            result.verifier_pass_count + result.verifier_fail_count
            <= result.passes_completed
        )
        assert result.sessions_consumed >= 0
        assert result.termination_reason in ImproveTermination
