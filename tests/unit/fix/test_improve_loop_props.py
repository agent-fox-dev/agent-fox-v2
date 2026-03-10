"""Improve loop property tests.

Test Spec: TS-31-P1 (termination bound)
Property: Property 2 from design.md
Requirements: 31-REQ-8.1
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.analyzer import AnalyzerResult
from agent_fox.fix.improve import run_improve_loop

from .conftest import make_improvement


def _make_verifier_pass_json() -> str:
    return json.dumps(
        {
            "quality_gates": "PASS",
            "improvement_valid": True,
            "verdict": "PASS",
            "evidence": "All good.",
        }
    )


class TestTerminationBound:
    """TS-31-P1: Improve loop never exceeds max_passes iterations."""

    @given(max_passes=st.integers(min_value=1, max_value=10))
    @settings(max_examples=10)
    @pytest.mark.asyncio
    async def test_passes_within_limit(self, max_passes: int) -> None:
        tmp_dir = Path("/tmp/test_improve_loop_props")
        config = AgentFoxConfig()

        analyzer_result = AnalyzerResult(
            improvements=[make_improvement(id="IMP-1", confidence="high")],
            summary="Test",
            diminishing_returns=False,
            raw_response="{}",
        )

        call_count = 0

        async def mock_runner(
            system_prompt: str, task_prompt: str, model_tier: str
        ) -> tuple[float, str]:
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:
                return (0.01, _make_verifier_pass_json())
            return (0.01, "completed")

        with (
            patch(
                "agent_fox.fix.improve.build_analyzer_prompt",
                return_value=("sys", "task"),
            ),
            patch(
                "agent_fox.fix.improve.parse_analyzer_response",
                return_value=analyzer_result,
            ),
            patch(
                "agent_fox.fix.improve.filter_improvements",
                return_value=analyzer_result.improvements,
            ),
            patch(
                "agent_fox.fix.improve.query_oracle_context",
                return_value="",
            ),
            patch(
                "agent_fox.fix.improve.load_review_context",
                return_value="",
            ),
            patch("agent_fox.fix.improve.subprocess.run"),
        ):
            result = await run_improve_loop(
                project_root=tmp_dir,
                config=config,
                max_passes=max_passes,
                remaining_budget=100.0,
                session_runner=mock_runner,
            )

        assert result.passes_completed <= max_passes
