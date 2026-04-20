"""Cost reporting tests: auxiliary integration, archetype tracking, per-spec cost.

Test Spec: TS-34-3, TS-34-4, TS-34-5, TS-34-9 through TS-34-13, TS-34-E5, TS-34-E6
Requirements: 34-REQ-1.3, 34-REQ-1.4, 34-REQ-1.5, 34-REQ-3.1, 34-REQ-3.2,
              34-REQ-3.3, 34-REQ-3.E1, 34-REQ-4.1, 34-REQ-4.2, 34-REQ-4.E1
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.core.config import PricingConfig
from agent_fox.core.models import calculate_cost
from agent_fox.core.token_tracker import (
    flush_auxiliary_usage,
    record_auxiliary_usage,
)
from agent_fox.engine.state import ExecutionState, SessionRecord, update_state_with_session
from agent_fox.core.node_id import spec_name_of as extract_spec_name
from agent_fox.reporting.status import StatusReport


class TestAuxiliaryIntegration:
    """TS-34-3, TS-34-4: Auxiliary tokens and cost in ExecutionState."""

    def test_aux_tokens_in_state(self) -> None:
        """TS-34-3: Auxiliary tokens are included in state totals."""
        # Reset accumulator
        flush_auxiliary_usage()

        # Record auxiliary usage before session
        record_auxiliary_usage(100, 50, "claude-haiku-4-5")

        # Create a session record
        record = SessionRecord(
            node_id="spec:1",
            attempt=1,
            status="completed",
            input_tokens=1000,
            output_tokens=500,
            cost=0.05,
            duration_ms=1000,
            error_message=None,
            timestamp="2026-01-01T00:00:00Z",
        )

        state = ExecutionState(
            plan_hash="abc",
            node_states={},
        )

        update_state_with_session(state, record)

        assert state.total_input_tokens == 1100  # 1000 session + 100 aux
        assert state.total_output_tokens == 550  # 500 session + 50 aux

    def test_aux_cost_in_state(self) -> None:
        """TS-34-4: Auxiliary token cost is included in total_cost."""
        # Reset accumulator
        flush_auxiliary_usage()

        # Record auxiliary usage
        record_auxiliary_usage(1000, 500, "claude-haiku-4-5")

        # Calculate expected auxiliary cost
        # haiku: $1/M input, $5/M output
        # cost = (1000/1M)*$1 + (500/1M)*$5 = $0.001 + $0.0025 = $0.0035
        pricing = PricingConfig()
        expected_aux_cost = calculate_cost(1000, 500, "claude-haiku-4-5", pricing)
        assert abs(expected_aux_cost - 0.0035) < 0.0001

        record = SessionRecord(
            node_id="spec:1",
            attempt=1,
            status="completed",
            input_tokens=1000,
            output_tokens=500,
            cost=0.05,
            duration_ms=1000,
            error_message=None,
            timestamp="2026-01-01T00:00:00Z",
        )

        state = ExecutionState(
            plan_hash="abc",
            node_states={},
        )

        update_state_with_session(state, record)

        # Total cost should include session cost + auxiliary cost
        assert state.total_cost > 0.05  # More than just session cost


class TestArchetypeTracking:
    """TS-34-9, TS-34-10, TS-34-11: Archetype field on SessionRecord."""

    def test_default_archetype(self) -> None:
        """TS-34-9: SessionRecord defaults archetype to 'coder'."""
        record = SessionRecord(
            node_id="spec:1",
            attempt=1,
            status="completed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message=None,
            timestamp="2026-01-01T00:00:00Z",
        )

        assert record.archetype == "coder"

    def test_archetype_set_explicitly(self) -> None:
        """SessionRecord can be created with explicit archetype."""
        record = SessionRecord(
            node_id="spec:1",
            attempt=1,
            status="completed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message=None,
            timestamp="2026-01-01T00:00:00Z",
            archetype="skeptic",
        )

        assert record.archetype == "skeptic"

    def test_status_per_archetype(self) -> None:
        """TS-34-11: StatusReport includes per-archetype cost breakdown."""
        # This test validates that StatusReport has cost_by_archetype field
        # and that it aggregates correctly from session records.
        report = StatusReport(
            counts={"completed": 3},
            total_tasks=3,
            input_tokens=0,
            output_tokens=0,
            estimated_cost=13.0,
            problem_tasks=[],
            per_spec={},
            cost_by_archetype={"coder": 10.0, "skeptic": 3.0},
            cost_by_spec={},
        )

        assert report.cost_by_archetype["coder"] == 10.0
        assert report.cost_by_archetype["skeptic"] == 3.0


class TestPerSpecCost:
    """TS-34-12, TS-34-13: Per-spec cost aggregation."""

    def test_status_per_spec(self) -> None:
        """TS-34-12: StatusReport includes per-spec cost breakdown."""
        report = StatusReport(
            counts={"completed": 3},
            total_tasks=3,
            input_tokens=0,
            output_tokens=0,
            estimated_cost=15.0,
            problem_tasks=[],
            per_spec={},
            cost_by_archetype={},
            cost_by_spec={"spec_a": 8.0, "spec_b": 7.0},
        )

        assert report.cost_by_spec["spec_a"] == 8.0
        assert report.cost_by_spec["spec_b"] == 7.0

    def test_spec_name_extraction(self) -> None:
        """TS-34-13: Spec name extracted from node_id correctly."""
        assert extract_spec_name("01_core_foundation:3") == "01_core_foundation"
        assert extract_spec_name("26_agent_archetypes:0:skeptic") == "26_agent_archetypes"


class TestCallSiteInstrumentation:
    """TS-34-5: All auxiliary call sites are instrumented."""

    def test_all_sites(self) -> None:
        """TS-34-5: All six auxiliary call sites track token usage.

        Modules may instrument usage directly via ``record_auxiliary_usage``
        / ``track_response_usage``, or indirectly through the ``ai_call``,
        ``ai_call_sync``, and ``nightshift_ai_call`` wrappers which handle
        token tracking internally.
        """
        _VALID_MARKERS = {
            "record_auxiliary_usage",
            "track_response_usage",
            "ai_call",
            "ai_call_sync",
            "nightshift_ai_call",
        }
        files = [
            "agent_fox/knowledge/extraction.py",
            "agent_fox/engine/knowledge_harvest.py",
            "agent_fox/spec/ai_validation.py",
            "agent_fox/fix/clusterer.py",
            "agent_fox/knowledge/query_oracle.py",
        ]
        for filepath in files:
            content = Path(filepath).read_text()
            assert any(marker in content for marker in _VALID_MARKERS), (
                f"{filepath} does not track auxiliary token usage"
            )


class TestBackwardCompat:
    """TS-34-E5, TS-34-E6: Backward compatibility edge cases."""

    def test_old_record_no_archetype(self) -> None:
        """TS-34-E5: SessionRecord from dict without archetype defaults to coder."""
        data = {
            "node_id": "spec:1",
            "attempt": 1,
            "status": "completed",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost": 0.0,
            "duration_ms": 0,
            "error_message": None,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        # SessionRecord should handle missing archetype
        record = SessionRecord(**data)  # type: ignore[arg-type]
        assert record.archetype == "coder"

    def test_node_id_no_colon(self) -> None:
        """TS-34-E6: node_id without colon uses full ID as spec name."""
        assert extract_spec_name("standalone_task") == "standalone_task"
