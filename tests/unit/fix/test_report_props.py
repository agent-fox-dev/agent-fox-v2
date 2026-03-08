"""Property tests for fix report.

Test Spec: TS-08-P5 (report field consistency)
Property: Property 5 from design.md
Requirements: 08-REQ-6.1, 08-REQ-6.2
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.fix.fix import FixResult, TerminationReason

# Strategy: generate valid FixResult instances
termination_reasons = st.sampled_from(list(TerminationReason))


@st.composite
def fix_result_st(draw):
    """Generate a valid FixResult."""
    passes = draw(st.integers(min_value=0, max_value=10))
    resolved = draw(st.integers(min_value=0, max_value=20))
    remaining = draw(st.integers(min_value=0, max_value=20))
    sessions = draw(st.integers(min_value=0, max_value=50))
    reason = draw(termination_reasons)
    return FixResult(
        passes_completed=passes,
        clusters_resolved=resolved,
        clusters_remaining=remaining,
        sessions_consumed=sessions,
        termination_reason=reason,
        remaining_failures=[],
    )


class TestReportFieldConsistency:
    """TS-08-P5: Report field consistency.

    Property 5: FixResult fields are internally consistent.
    """

    @given(result=fix_result_st())
    @settings(max_examples=50)
    def test_fields_are_non_negative(self, result: FixResult) -> None:
        """All numeric fields are non-negative."""
        assert result.passes_completed >= 0
        assert result.clusters_resolved >= 0
        assert result.clusters_remaining >= 0
        assert result.sessions_consumed >= 0

    @given(result=fix_result_st())
    @settings(max_examples=50)
    def test_termination_reason_is_valid(self, result: FixResult) -> None:
        """Termination reason is a valid enum value."""
        assert result.termination_reason in TerminationReason
