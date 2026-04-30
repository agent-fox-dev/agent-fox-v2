"""Improve loop tests.

Test Spec: TS-31-19 through TS-31-25
Requirements: 31-REQ-2.3, 31-REQ-3.E2, 31-REQ-5.E1, 31-REQ-7.1, 31-REQ-7.2,
              31-REQ-8.1, 31-REQ-8.2, 31-REQ-8.3
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.analyzer import AnalyzerResult, Improvement
from agent_fox.fix.improve import (
    ImproveTermination,
    run_improve_loop,
)

from .conftest import make_improvement


def _make_analyzer_result(
    diminishing_returns: bool = False,
    improvements: list[Improvement] | None = None,
) -> AnalyzerResult:
    """Helper to create AnalyzerResult for tests."""
    if improvements is None:
        improvements = [
            make_improvement(id="IMP-1", confidence=0.9),
        ]
    return AnalyzerResult(
        improvements=improvements,
        summary="Test summary",
        diminishing_returns=diminishing_returns,
        raw_response="{}",
    )


def _make_verifier_pass_json() -> str:
    return json.dumps(
        {
            "quality_gates": "PASS",
            "improvement_valid": True,
            "verdict": "PASS",
            "evidence": "All good.",
        }
    )


def _make_verifier_fail_json() -> str:
    return json.dumps(
        {
            "quality_gates": "PASS",
            "improvement_valid": False,
            "verdict": "FAIL",
            "evidence": "Public API changed.",
        }
    )


class TestImproveLoopTermination:
    """TS-31-19 through TS-31-25: Improve loop termination conditions."""

    @pytest.mark.asyncio
    async def test_diminishing_returns_converges(self, tmp_path: Path, mock_config: AgentFoxConfig) -> None:
        """TS-31-19: Loop stops on diminishing returns."""
        analyzer_result = _make_analyzer_result(diminishing_returns=True)

        async def mock_runner(system_prompt: str, task_prompt: str, model_tier: str) -> tuple[float, str]:
            return (0.10, analyzer_result.raw_response)

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
                "agent_fox.fix.improve.query_oracle_context",
                return_value="",
            ),
            patch(
                "agent_fox.fix.improve.load_review_context",
                return_value="",
            ),
        ):
            result = await run_improve_loop(
                project_root=tmp_path,
                config=mock_config,
                max_passes=3,
                remaining_budget=10.0,
                session_runner=mock_runner,
            )

        assert result.termination_reason == ImproveTermination.CONVERGED

    @pytest.mark.asyncio
    async def test_zero_actionable_improvements_converges(self, tmp_path: Path, mock_config: AgentFoxConfig) -> None:
        """TS-31-20: Loop stops when no high/medium confidence improvements."""
        low_only = _make_analyzer_result(
            improvements=[make_improvement(id="L1", confidence=0.3)],
        )

        async def mock_runner(system_prompt: str, task_prompt: str, model_tier: str) -> tuple[float, str]:
            return (0.10, low_only.raw_response)

        with (
            patch(
                "agent_fox.fix.improve.build_analyzer_prompt",
                return_value=("sys", "task"),
            ),
            patch(
                "agent_fox.fix.improve.parse_analyzer_response",
                return_value=low_only,
            ),
            patch(
                "agent_fox.fix.improve.query_oracle_context",
                return_value="",
            ),
            patch(
                "agent_fox.fix.improve.load_review_context",
                return_value="",
            ),
        ):
            result = await run_improve_loop(
                project_root=tmp_path,
                config=mock_config,
                max_passes=3,
                remaining_budget=10.0,
                session_runner=mock_runner,
            )

        assert result.termination_reason == ImproveTermination.CONVERGED

    @pytest.mark.asyncio
    async def test_pass_limit_reached(self, tmp_path: Path, mock_config: AgentFoxConfig) -> None:
        """TS-31-21: Loop stops after max_passes."""
        analyzer_result = _make_analyzer_result()

        call_count = 0

        async def mock_runner(system_prompt: str, task_prompt: str, model_tier: str) -> tuple[float, str]:
            nonlocal call_count
            call_count += 1
            # Return verifier PASS JSON on verifier calls (every 3rd call)
            if call_count % 3 == 0:
                return (0.05, _make_verifier_pass_json())
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
            patch(
                "agent_fox.fix.improve.run_git_sync",
                return_value=(0, "", ""),
            ),
        ):
            result = await run_improve_loop(
                project_root=tmp_path,
                config=mock_config,
                max_passes=2,
                remaining_budget=10.0,
                session_runner=mock_runner,
            )

        assert result.termination_reason == ImproveTermination.PASS_LIMIT
        assert result.passes_completed == 2

    @pytest.mark.asyncio
    async def test_verifier_fail_triggers_rollback(self, tmp_path: Path, mock_config: AgentFoxConfig) -> None:
        """TS-31-22: Verifier FAIL triggers rollback and termination."""
        analyzer_result = _make_analyzer_result()

        call_count = 0

        async def mock_runner(system_prompt: str, task_prompt: str, model_tier: str) -> tuple[float, str]:
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:
                return (0.05, _make_verifier_fail_json())
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
            patch(
                "agent_fox.fix.improve.run_git_sync",
                return_value=(0, "", ""),
            ),
        ):
            result = await run_improve_loop(
                project_root=tmp_path,
                config=mock_config,
                max_passes=3,
                remaining_budget=10.0,
                session_runner=mock_runner,
            )

        assert result.termination_reason == ImproveTermination.VERIFIER_FAIL
        assert result.pass_results[0].rolled_back is True

    @pytest.mark.asyncio
    async def test_cost_limit_terminates(self, tmp_path: Path, mock_config: AgentFoxConfig) -> None:
        """TS-31-23: Loop stops when cost budget is exhausted."""
        with (
            patch("agent_fox.fix.improve.query_oracle_context", return_value=""),
            patch("agent_fox.fix.improve.load_review_context", return_value=""),
        ):
            result = await run_improve_loop(
                project_root=tmp_path,
                config=mock_config,
                max_passes=3,
                remaining_budget=0.01,
            )

        assert result.termination_reason == ImproveTermination.COST_LIMIT
        assert result.passes_completed == 0

    @pytest.mark.asyncio
    async def test_analyzer_failure_terminates(self, tmp_path: Path, mock_config: AgentFoxConfig) -> None:
        """TS-31-24: Analyzer session failure terminates loop."""

        async def failing_runner(system_prompt: str, task_prompt: str, model_tier: str) -> tuple[float, str]:
            raise RuntimeError("Backend error")

        with (
            patch(
                "agent_fox.fix.improve.build_analyzer_prompt",
                return_value=("sys", "task"),
            ),
            patch(
                "agent_fox.fix.improve.query_oracle_context",
                return_value="",
            ),
            patch(
                "agent_fox.fix.improve.load_review_context",
                return_value="",
            ),
        ):
            result = await run_improve_loop(
                project_root=tmp_path,
                config=mock_config,
                max_passes=3,
                remaining_budget=10.0,
                session_runner=failing_runner,
            )

        assert result.termination_reason == ImproveTermination.ANALYZER_ERROR

    @pytest.mark.asyncio
    async def test_coder_failure_terminates(self, tmp_path: Path, mock_config: AgentFoxConfig) -> None:
        """TS-31-25: Coder failure terminates loop and discards changes."""
        analyzer_result = _make_analyzer_result()

        call_count = 0

        async def mock_runner(system_prompt: str, task_prompt: str, model_tier: str) -> tuple[float, str]:
            nonlocal call_count
            call_count += 1
            # First call is analyzer (succeeds), second is coder (fails)
            if call_count == 1:
                return (0.10, "completed")
            raise RuntimeError("Coder session failed")

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
            patch(
                "agent_fox.fix.improve.run_git_sync",
                return_value=(0, "", ""),
            ),
        ):
            result = await run_improve_loop(
                project_root=tmp_path,
                config=mock_config,
                max_passes=3,
                remaining_budget=10.0,
                session_runner=mock_runner,
            )

        assert result.termination_reason == ImproveTermination.CODER_ERROR
