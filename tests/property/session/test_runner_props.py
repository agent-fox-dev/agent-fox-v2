"""Property tests for SessionOutcome field validation.

Test Spec: TS-03-P2 (SessionOutcome fields are well-formed)
Property: Property 3 from design.md
Requirements: 03-REQ-3.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.sink import SessionOutcome

# Strategy for valid status values
status_strategy = st.sampled_from(["completed", "failed", "timeout"])


class TestSessionOutcomeFieldsWellFormed:
    """TS-03-P2: SessionOutcome fields are well-formed.

    Property 3: Every SessionOutcome has valid field values.
    """

    @given(
        spec_name=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
            min_size=1,
            max_size=50,
        ),
        task_group=st.from_regex(r"[0-9]{1,4}", fullmatch=True),
        node_id=st.text(min_size=1, max_size=20),
        status=status_strategy,
        input_tokens=st.integers(min_value=0, max_value=10_000_000),
        output_tokens=st.integers(min_value=0, max_value=10_000_000),
        duration_ms=st.integers(min_value=0, max_value=3_600_000),
    )
    @settings(max_examples=100)
    def test_outcome_fields_valid(
        self,
        spec_name: str,
        task_group: str,
        node_id: str,
        status: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
    ) -> None:
        """SessionOutcome fields satisfy all invariants."""
        outcome = SessionOutcome(
            spec_name=spec_name,
            task_group=task_group,
            node_id=node_id,
            status=status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
        )

        assert len(outcome.spec_name) > 0
        assert outcome.task_group.isdigit()
        assert outcome.status in ("completed", "failed", "timeout")
        assert outcome.input_tokens >= 0
        assert outcome.output_tokens >= 0
        assert outcome.duration_ms >= 0

    @given(status=status_strategy)
    @settings(max_examples=20)
    def test_status_is_one_of_valid_values(self, status: str) -> None:
        """Status is always one of the three valid values."""
        outcome = SessionOutcome(
            spec_name="test",
            task_group="1",
            node_id="test:1",
            status=status,
        )
        assert outcome.status in ("completed", "failed", "timeout")
