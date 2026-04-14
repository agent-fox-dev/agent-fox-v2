"""Property-based tests for AgentTraceSink and truncate_tool_input.

Test Spec: TS-103-P1 (event completeness), TS-103-P2 (truncation invariants),
           TS-103-P3 (file location correctness)
Properties: Properties 1-3 from design.md
Requirements: 103-REQ-1.2, 103-REQ-2.1, 103-REQ-3.1, 103-REQ-4.1,
              103-REQ-4.2, 103-REQ-4.3, 103-REQ-4.E1, 103-REQ-6.1,
              103-REQ-7.3
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_fox.knowledge.agent_trace import AgentTraceSink, truncate_tool_input
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for run_id values (format: YYYYMMDD_HHMMSS_hhhhhhh)
_run_id_strategy = st.from_regex(r"\d{8}_\d{6}_[0-9a-f]{6}", fullmatch=True)

# Strategy for mixed tool_input values (strings, ints, bools, lists)
_mixed_value_strategy = st.one_of(
    st.text(min_size=0, max_size=20_000),
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.booleans(),
    st.lists(st.text(min_size=0, max_size=10), min_size=0, max_size=5),
)

_tool_input_strategy = st.dictionaries(
    keys=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    values=_mixed_value_strategy,
    min_size=0,
    max_size=10,
)

# Call type indices for TS-103-P1: each index maps to a record method
_CALL_SESSION_INIT = 0
_CALL_ASSISTANT_MESSAGE = 1
_CALL_TOOL_USE = 2
_CALL_SESSION_RESULT = 3
_CALL_TYPES = [_CALL_SESSION_INIT, _CALL_ASSISTANT_MESSAGE, _CALL_TOOL_USE, _CALL_SESSION_RESULT]


def _dispatch_call(sink: AgentTraceSink, call_type: int, run_id: str) -> None:
    """Dispatch a single record call based on call_type index."""
    node_id = "test_node"
    if call_type == _CALL_SESSION_INIT:
        sink.record_session_init(
            run_id=run_id,
            node_id=node_id,
            model_id="claude-sonnet-4-6",
            archetype="coder",
            system_prompt="sys",
            task_prompt="task",
        )
    elif call_type == _CALL_ASSISTANT_MESSAGE:
        sink.record_assistant_message(
            run_id=run_id,
            node_id=node_id,
            content="assistant response",
        )
    elif call_type == _CALL_TOOL_USE:
        sink.record_tool_use(
            run_id=run_id,
            node_id=node_id,
            tool_name="Read",
            tool_input={"file_path": "/tmp/f.py"},
        )
    elif call_type == _CALL_SESSION_RESULT:
        sink.record_session_result(
            run_id=run_id,
            node_id=node_id,
            status="completed",
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            duration_ms=500,
            is_error=False,
            error_message=None,
        )


def _read_lines(path: Path) -> list[str]:
    """Read non-empty JSONL lines from the trace file."""
    if not path.exists():
        return []
    return [line for line in path.read_text().split("\n") if line.strip()]


# ---------------------------------------------------------------------------
# TS-103-P1: Event Completeness
# ---------------------------------------------------------------------------


class TestEventCompleteness:
    """TS-103-P1: For any sequence of record calls, file has exactly that many lines.

    Property 1 from design.md.
    Requirements: 103-REQ-2.1, 103-REQ-3.1, 103-REQ-4.1, 103-REQ-6.1
    """

    @given(
        call_types=st.lists(
            st.sampled_from(_CALL_TYPES),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=50)
    def test_event_completeness(self, tmp_path: Path, call_types: list[int]) -> None:
        """Number of lines equals number of record calls, all valid JSON."""
        import uuid

        # Use a unique run_id per Hypothesis iteration to avoid file accumulation
        run_id = f"20260101_000000_{uuid.uuid4().hex[:6]}"
        audit_dir = tmp_path / run_id
        audit_dir.mkdir(parents=True, exist_ok=True)

        sink = AgentTraceSink(audit_dir, run_id)
        for call_type in call_types:
            _dispatch_call(sink, call_type, run_id)

        trace_path = audit_dir / f"agent_{run_id}.jsonl"
        lines = _read_lines(trace_path)

        assert len(lines) == len(call_types), f"Expected {len(call_types)} lines, got {len(lines)}"
        for line in lines:
            parsed = json.loads(line)
            assert "event_type" in parsed
            assert "run_id" in parsed


# ---------------------------------------------------------------------------
# TS-103-P2: Truncation Preserves Keys and Respects max_len
# ---------------------------------------------------------------------------


class TestTruncationInvariants:
    """TS-103-P2: truncate_tool_input preserves keys, truncates strings correctly.

    Property 2 from design.md.
    Requirements: 103-REQ-4.2, 103-REQ-4.3, 103-REQ-4.E1
    """

    @given(
        tool_input=_tool_input_strategy,
        max_len=st.integers(min_value=100, max_value=20_000),
    )
    @settings(max_examples=100)
    def test_truncation_invariants(self, tool_input: dict, max_len: int) -> None:
        """Keys preserved; strings truncated at max_len with marker; non-strings unchanged."""
        result = truncate_tool_input(tool_input, max_len=max_len)

        # Keys must be identical
        assert set(result.keys()) == set(tool_input.keys())

        for key in tool_input:
            original = tool_input[key]
            truncated = result[key]

            if isinstance(original, str):
                if len(original) <= max_len:
                    # Short strings: unchanged
                    assert truncated == original, (
                        f"Key {key!r}: expected unchanged string {original!r}, got {truncated!r}"
                    )
                else:
                    # Long strings: truncated to exactly max_len + " [truncated]"
                    expected = original[:max_len] + " [truncated]"
                    assert truncated == expected, f"Key {key!r}: expected truncated string, got {truncated!r}"
            else:
                # Non-string values: identical (not copied, same value)
                assert truncated == original, f"Key {key!r}: non-string value changed: {original!r} → {truncated!r}"

    def test_empty_dict_unchanged(self) -> None:
        """Empty dict returns empty dict."""
        result = truncate_tool_input({})
        assert result == {}

    def test_default_max_len_is_ten_thousand(self) -> None:
        """Default max_len is 10,000."""
        long_str = "a" * 15_000
        result = truncate_tool_input({"key": long_str})
        assert result["key"] == "a" * 10_000 + " [truncated]"

    def test_returns_shallow_copy(self) -> None:
        """truncate_tool_input returns a new dict (shallow copy)."""
        original = {"key": "value"}
        result = truncate_tool_input(original)
        assert result is not original


# ---------------------------------------------------------------------------
# TS-103-P3: File Location Correctness
# ---------------------------------------------------------------------------


class TestFileLocation:
    """TS-103-P3: The trace file is always at the canonical path.

    Property 3 from design.md.
    Requirements: 103-REQ-1.2, 103-REQ-7.3
    """

    @given(run_id=_run_id_strategy)
    @settings(max_examples=30)
    def test_file_location(self, tmp_path: Path, run_id: str) -> None:
        """After any write, the trace file is at agent_{run_id}.jsonl."""
        import uuid

        # Use a unique subdirectory per iteration to prevent file accumulation
        audit_dir = tmp_path / uuid.uuid4().hex
        audit_dir.mkdir(parents=True, exist_ok=True)

        sink = AgentTraceSink(audit_dir, run_id)
        sink.record_session_init(
            run_id=run_id,
            node_id="n1",
            model_id="claude-sonnet-4-6",
            archetype="coder",
            system_prompt="sys",
            task_prompt="task",
        )

        agent_files = list(audit_dir.glob("agent_*.jsonl"))
        assert len(agent_files) == 1, f"Expected exactly 1 agent_*.jsonl, found {len(agent_files)}: {agent_files}"
        assert agent_files[0].name == f"agent_{run_id}.jsonl"
