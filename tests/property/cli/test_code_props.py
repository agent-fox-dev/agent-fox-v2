"""Property tests for the code command.

Test Spec: TS-16-P1 (exit code mapping), TS-16-P2 (override preservation)
Properties: Property 1 (exit code consistency), Property 2 (override preservation)
Requirements: 16-REQ-2.1, 16-REQ-2.3, 16-REQ-2.4, 16-REQ-2.5,
              16-REQ-4.1, 16-REQ-4.2, 16-REQ-4.3, 16-REQ-4.4,
              16-REQ-4.5, 16-REQ-4.E1
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import OrchestratorConfig

# Known exit code mapping from design.md
_EXPECTED_EXIT_CODES = {
    "completed": 0,
    "stalled": 2,
    "cost_limit": 3,
    "session_limit": 3,
    "interrupted": 130,
}

_KNOWN_STATUSES = list(_EXPECTED_EXIT_CODES.keys())


class TestExitCodeMappingConsistency:
    """TS-16-P1: Exit code mapping consistency.

    Property 1: For any run_status string, the exit code function always
    returns the correct mapping, defaulting to 1 for unknown values.

    Requirements: 16-REQ-4.1, 16-REQ-4.2, 16-REQ-4.3, 16-REQ-4.4,
                  16-REQ-4.5, 16-REQ-4.E1
    """

    @given(status=st.sampled_from(_KNOWN_STATUSES))
    @settings(max_examples=20)
    def test_known_statuses_map_correctly(self, status: str) -> None:
        """Known run statuses produce the documented exit code."""
        from agent_fox.cli.code import _exit_code_for_status  # type: ignore[import-not-found]  # noqa: I001

        result = _exit_code_for_status(status)
        assert result == _EXPECTED_EXIT_CODES[status], (
            f"Expected exit code {_EXPECTED_EXIT_CODES[status]} for "
            f"status '{status}', got {result}"
        )

    @given(
        status=st.text(min_size=1, max_size=50).filter(
            lambda s: s not in _KNOWN_STATUSES
        )
    )
    @settings(max_examples=50)
    def test_unknown_statuses_default_to_1(self, status: str) -> None:
        """Unknown run statuses default to exit code 1."""
        from agent_fox.cli.code import _exit_code_for_status  # type: ignore[import-not-found]  # noqa: I001

        result = _exit_code_for_status(status)
        assert result == 1, (
            f"Expected exit code 1 for unknown status '{status}', got {result}"
        )


class TestOverridePreservation:
    """TS-16-P2: Override preservation.

    Property 2: CLI overrides are applied correctly while preserving
    all non-overridden fields from the original config.

    Requirements: 16-REQ-2.1, 16-REQ-2.3, 16-REQ-2.4, 16-REQ-2.5
    """

    @given(
        parallel=st.one_of(st.none(), st.integers(min_value=1, max_value=8)),
        max_cost=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1000.0)),
        max_sessions=st.one_of(st.none(), st.integers(min_value=1, max_value=1000)),
    )
    @settings(max_examples=100)
    def test_overrides_applied_and_defaults_preserved(
        self,
        parallel: int | None,
        max_cost: float | None,
        max_sessions: int | None,
    ) -> None:
        """Overridden fields take the new value; others keep the default."""
        from agent_fox.engine.run import _apply_overrides  # type: ignore[import-not-found]  # noqa: I001

        default_config = OrchestratorConfig()
        result = _apply_overrides(default_config, parallel, max_cost, max_sessions)

        # Overridden fields must match the provided value
        if parallel is not None:
            assert result.parallel == parallel
        else:
            assert result.parallel == default_config.parallel

        if max_cost is not None:
            assert result.max_cost == max_cost
        else:
            assert result.max_cost == default_config.max_cost

        if max_sessions is not None:
            assert result.max_sessions == max_sessions
        else:
            assert result.max_sessions == default_config.max_sessions

        # Non-overridden fields must remain unchanged
        assert result.max_retries == default_config.max_retries
        assert result.sync_interval == default_config.sync_interval
        assert result.hot_load == default_config.hot_load
        assert result.session_timeout == default_config.session_timeout
        assert result.inter_session_delay == default_config.inter_session_delay
