"""Improve cost property tests.

Test Spec: TS-31-P4 (cost budget monotonicity)
Property: Property 4 from design.md
Requirements: 31-REQ-2.3, 31-REQ-8.3
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


class TestCostBudgetMonotonicity:
    """TS-31-P4: Cumulative cost never exceeds budget."""

    @given(budget=st.floats(min_value=0.01, max_value=10.0))
    @settings(max_examples=10)
    @pytest.mark.asyncio
    async def test_cost_within_budget(self, budget: float) -> None:
        tmp_dir = Path("/tmp/test_improve_cost_props")
        config = AgentFoxConfig()

        analyzer_result = AnalyzerResult(
            improvements=[make_improvement(id="IMP-1", confidence=0.9)],
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
                return (0.10, _make_verifier_pass_json())
            return (0.10, "completed")

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
                max_passes=10,
                remaining_budget=budget,
                session_runner=mock_runner,
            )

        # Allow small floating point tolerance
        assert result.total_cost <= budget + 0.001
