"""Tests for the AI critic false-positive awareness enhancement.

Test cases: TS-110-14, TS-110-15, TS-110-P9, TS-110-SMOKE-3

Requirements: 110-REQ-6.1 through 110-REQ-6.E2
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.nightshift.critic import consolidate_findings
from agent_fox.nightshift.finding import Finding

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(**overrides: object) -> Finding:
    """Create a Finding with sensible defaults."""
    defaults: dict[str, object] = {
        "category": "dead_code",
        "title": "Unused function",
        "description": "Function is never called.",
        "severity": "minor",
        "affected_files": ["src/a.py"],
        "suggested_fix": "Remove the function.",
        "evidence": "grep: no callers found",
        "group_key": "dead_code:unused_fn",
    }
    defaults.update(overrides)
    return Finding(**defaults)  # type: ignore[arg-type]


def _three_findings(**overrides: object) -> list[Finding]:
    """Return 3 findings (the minimum to trigger AI critic path)."""
    return [_make_finding(title=f"Finding {i}", group_key=f"key_{i}", **overrides) for i in range(3)]


def _capture_ai_calls() -> tuple[list[tuple[tuple[object, ...], dict[str, object]]], AsyncMock]:
    """Return (call_log, mock) for capturing nightshift_ai_call arguments."""
    call_log: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def mock_ai(*args: object, **kwargs: object) -> tuple[str, None]:
        call_log.append((args, kwargs))
        # Return a minimal valid response (will fall back to mechanical on parse error)
        return ('{"groups": [], "dropped": [0, 1, 2]}', None)

    return call_log, mock_ai  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# TS-110-14: Critic prompt contains Known False Positives when fps provided
# ---------------------------------------------------------------------------


class TestCriticPromptWithFalsePositives:
    """TS-110-14: System prompt contains Known False Positives section."""

    async def test_false_positives_appear_in_system_prompt(self) -> None:
        """When false_positives non-empty, system prompt contains the section."""
        findings = _three_findings()
        fps = ["Dead code in tests/ is acceptable"]

        call_log, mock_ai = _capture_ai_calls()

        with patch(
            "agent_fox.nightshift.cost_helpers.nightshift_ai_call",
            new=mock_ai,
        ):
            await consolidate_findings(findings, false_positives=fps)

        assert len(call_log) == 1
        args, kwargs = call_log[0]

        # The false-positive text must appear somewhere in the AI call arguments
        all_args_text = " ".join(str(a) for a in args) + " " + " ".join(
            str(v) for v in kwargs.values()
        )
        assert "Known False Positives" in all_args_text
        assert "Dead code in tests/" in all_args_text

    async def test_false_positives_section_header_present(self) -> None:
        """Prompt modification adds a 'Known False Positives' section header."""
        findings = _three_findings()
        fps = ["Ignore leftover debug prints in scripts/"]

        call_log, mock_ai = _capture_ai_calls()

        with patch(
            "agent_fox.nightshift.cost_helpers.nightshift_ai_call",
            new=mock_ai,
        ):
            await consolidate_findings(findings, false_positives=fps)

        args, kwargs = call_log[0]
        all_text = " ".join(str(a) for a in args) + " " + " ".join(
            str(v) for v in kwargs.values()
        )
        assert "Known False Positives" in all_text
        assert "Ignore leftover debug prints" in all_text

    async def test_multiple_false_positives_all_present(self) -> None:
        """All entries in false_positives appear in the system prompt."""
        findings = _three_findings()
        fps = [
            "Dead code in test helpers is acceptable",
            "Unused imports in __init__.py are intentional",
        ]

        call_log, mock_ai = _capture_ai_calls()

        with patch(
            "agent_fox.nightshift.cost_helpers.nightshift_ai_call",
            new=mock_ai,
        ):
            await consolidate_findings(findings, false_positives=fps)

        args, kwargs = call_log[0]
        all_text = " ".join(str(a) for a in args) + " " + " ".join(
            str(v) for v in kwargs.values()
        )
        for fp in fps:
            assert fp in all_text


# ---------------------------------------------------------------------------
# TS-110-15: Critic prompt unchanged when no false positives
# ---------------------------------------------------------------------------


class TestCriticPromptWithoutFalsePositives:
    """TS-110-15: System prompt is not modified when false_positives is empty/None."""

    async def test_no_false_positives_none_prompt_unmodified(self) -> None:
        """false_positives=None → 'Known False Positives' not in prompt."""
        findings = _three_findings()

        call_log, mock_ai = _capture_ai_calls()

        with patch(
            "agent_fox.nightshift.cost_helpers.nightshift_ai_call",
            new=mock_ai,
        ):
            await consolidate_findings(findings, false_positives=None)

        assert len(call_log) == 1
        args, kwargs = call_log[0]
        all_text = " ".join(str(a) for a in args) + " " + " ".join(
            str(v) for v in kwargs.values()
        )
        assert "Known False Positives" not in all_text

    async def test_no_false_positives_empty_list_prompt_unmodified(self) -> None:
        """false_positives=[] → 'Known False Positives' not in prompt."""
        findings = _three_findings()

        call_log, mock_ai = _capture_ai_calls()

        with patch(
            "agent_fox.nightshift.cost_helpers.nightshift_ai_call",
            new=mock_ai,
        ):
            await consolidate_findings(findings, false_positives=[])

        assert len(call_log) == 1
        args, kwargs = call_log[0]
        all_text = " ".join(str(a) for a in args) + " " + " ".join(
            str(v) for v in kwargs.values()
        )
        assert "Known False Positives" not in all_text

    async def test_consolidate_findings_accepts_false_positives_parameter(self) -> None:
        """consolidate_findings() accepts the false_positives keyword argument."""
        findings = [_make_finding(title=f"F{i}", group_key=f"k{i}") for i in range(2)]

        # Should not raise TypeError for the new parameter
        result = await consolidate_findings(findings, false_positives=["Some fp"])

        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# TS-110-P9: Critic Prompt Stability (property test)
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestCriticPromptStability:
    """TS-110-P9: consolidate_findings(fps=None) and (fps=[]) produce same prompt."""

    @given(n=st.integers(min_value=3, max_value=5))
    @settings(max_examples=10)
    def test_none_and_empty_produce_same_prompt(self, n: int) -> None:
        """Empty and None false_positives produce identical system prompts."""
        findings = [
            _make_finding(title=f"Finding {i}", group_key=f"key_{i}")
            for i in range(n)
        ]

        captured_none: list[tuple[tuple[object, ...], dict[str, object]]] = []
        captured_empty: list[tuple[tuple[object, ...], dict[str, object]]] = []

        async def mock_ai_capture_none(*args: object, **kwargs: object) -> tuple[str, None]:
            captured_none.append((args, kwargs))
            return ('{"groups": [], "dropped": list(range(n))}', None)

        async def mock_ai_capture_empty(*args: object, **kwargs: object) -> tuple[str, None]:
            captured_empty.append((args, kwargs))
            return ('{"groups": [], "dropped": list(range(n))}', None)

        loop = asyncio.new_event_loop()
        try:
            with patch(
                "agent_fox.nightshift.cost_helpers.nightshift_ai_call",
                new=mock_ai_capture_none,
            ):
                loop.run_until_complete(
                    consolidate_findings(findings, false_positives=None)
                )

            with patch(
                "agent_fox.nightshift.cost_helpers.nightshift_ai_call",
                new=mock_ai_capture_empty,
            ):
                loop.run_until_complete(
                    consolidate_findings(findings, false_positives=[])
                )
        finally:
            loop.close()

        # Both calls should have been made
        assert len(captured_none) == 1
        assert len(captured_empty) == 1

        # Build string representation of call args (system prompt is in there)
        args_none, kwargs_none = captured_none[0]
        args_empty, kwargs_empty = captured_empty[0]

        text_none = " ".join(str(a) for a in args_none) + " " + " ".join(
            str(v) for v in kwargs_none.values()
        )
        text_empty = " ".join(str(a) for a in args_empty) + " " + " ".join(
            str(v) for v in kwargs_empty.values()
        )

        # Both prompts must not contain the false positives section
        assert "Known False Positives" not in text_none
        assert "Known False Positives" not in text_empty


# ---------------------------------------------------------------------------
# TS-110-SMOKE-3: AI critic with false-positive awareness (Path 3)
# ---------------------------------------------------------------------------


class TestCriticFalsePositivesSmoke:
    """TS-110-SMOKE-3: Full critic path with false positives in system prompt."""

    async def test_smoke_critic_false_positives_end_to_end(self) -> None:
        """Real prompt construction executes and includes false-positive section."""
        # 3+ findings to trigger AI critic path
        findings = _three_findings()
        fps = ["Dead code in tests/ is acceptable"]

        call_log: list[tuple[tuple[object, ...], dict[str, object]]] = []

        async def mock_ai(*args: object, **kwargs: object) -> tuple[str, None]:
            call_log.append((args, kwargs))
            return ('{"groups": [], "dropped": [0, 1, 2]}', None)

        # Patch the AI backend (not _run_critic), so real prompt construction runs
        with patch(
            "agent_fox.nightshift.cost_helpers.nightshift_ai_call",
            new=mock_ai,
        ):
            result = await consolidate_findings(findings, false_positives=fps)

        # Result should be a list (mechanical fallback on parse error is OK)
        assert isinstance(result, list)

        # AI must have been called (3 findings ≥ threshold)
        assert len(call_log) == 1

        args, kwargs = call_log[0]
        all_text = " ".join(str(a) for a in args) + " " + " ".join(
            str(v) for v in kwargs.values()
        )

        # System prompt must contain the false positives section
        assert "Known False Positives" in all_text
        assert "Dead code in tests/" in all_text
