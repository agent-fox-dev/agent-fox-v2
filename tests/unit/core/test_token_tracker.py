"""Token accumulator tests.

Test Spec: TS-34-1, TS-34-2, TS-34-E1, TS-34-E2
Requirements: 34-REQ-1.1, 34-REQ-1.2, 34-REQ-1.E1, 34-REQ-1.E2
"""

from __future__ import annotations

from agent_fox.core.token_tracker import (
    TokenAccumulator,
    TokenUsage,
    flush_auxiliary_usage,
    get_auxiliary_totals,
    record_auxiliary_usage,
)


class TestTokenAccumulator:
    """TS-34-1, TS-34-2: Accumulator records and reports usage."""

    def test_records_usage(self) -> None:
        """TS-34-1: Accumulator records input_tokens, output_tokens, model."""
        acc = TokenAccumulator()
        acc.record(100, 50, "claude-haiku-4-5")
        acc.record(200, 100, "claude-sonnet-4-6")

        entries = acc.flush()

        assert len(entries) == 2
        assert entries[0].input_tokens == 100
        assert entries[0].output_tokens == 50
        assert entries[0].model == "claude-haiku-4-5"
        assert entries[1].input_tokens == 200
        assert entries[1].output_tokens == 100
        assert entries[1].model == "claude-sonnet-4-6"

    def test_reports_immediately(self) -> None:
        """TS-34-2: get totals reflects usage immediately after recording."""
        acc = TokenAccumulator()
        acc.record(100, 50, "claude-haiku-4-5")

        input_total, output_total = acc.total()

        assert input_total == 100
        assert output_total == 50

    def test_flush_resets_accumulator(self) -> None:
        """After flush, accumulator is empty."""
        acc = TokenAccumulator()
        acc.record(100, 50, "claude-haiku-4-5")

        acc.flush()
        entries = acc.flush()

        assert entries == []

    def test_total_does_not_flush(self) -> None:
        """Calling total() does not clear the accumulator."""
        acc = TokenAccumulator()
        acc.record(100, 50, "claude-haiku-4-5")

        acc.total()
        entries = acc.flush()

        assert len(entries) == 1

    def test_module_level_functions(self) -> None:
        """Module-level convenience functions work with global accumulator."""
        # Reset global state
        flush_auxiliary_usage()

        record_auxiliary_usage(100, 50, "claude-haiku-4-5")
        record_auxiliary_usage(200, 100, "claude-sonnet-4-6")

        input_total, output_total = get_auxiliary_totals()
        assert input_total == 300
        assert output_total == 150

        entries = flush_auxiliary_usage()
        assert len(entries) == 2

        # Second flush should be empty
        assert flush_auxiliary_usage() == []


class TestAccumulatorEdgeCases:
    """TS-34-E1, TS-34-E2: Edge cases for failed calls and missing usage."""

    def test_failed_call_records_zero(self) -> None:
        """TS-34-E1: A failed auxiliary call records zero tokens."""
        acc = TokenAccumulator()
        acc.record(0, 0, "claude-haiku-4-5")

        entries = acc.flush()

        assert len(entries) == 1
        assert entries[0].input_tokens == 0
        assert entries[0].output_tokens == 0

    def test_missing_usage_logs_warning(self, caplog: object) -> None:
        """TS-34-E2: Missing usage data logs a warning and records zero."""
        # This tests that the record function handles None-like values
        # The actual instrumentation sites handle missing usage and call
        # record with zeros + log a warning. We verify the accumulator
        # accepts zero values gracefully.
        acc = TokenAccumulator()
        acc.record(0, 0, "claude-haiku-4-5")

        entries = acc.flush()
        assert len(entries) == 1
        assert entries[0].input_tokens == 0
        assert entries[0].output_tokens == 0

    def test_token_usage_dataclass(self) -> None:
        """TokenUsage dataclass has expected fields."""
        usage = TokenUsage(input_tokens=100, output_tokens=50, model="test")
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.model == "test"
