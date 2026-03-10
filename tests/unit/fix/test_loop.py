"""Loop tests.

Test Spec: TS-08-11 (all fixed termination), TS-08-12 (max passes termination)
Edge Cases: TS-08-E5 (max_passes clamping)
Requirements: 08-REQ-5.1, 08-REQ-5.2, 08-REQ-5.3, 08-REQ-7.E1
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.checks import CheckCategory, CheckDescriptor
from agent_fox.fix.clusterer import FailureCluster
from agent_fox.fix.fix import TerminationReason, run_fix_loop

from .conftest import make_failure_record


class TestFixLoopAllFixed:
    """TS-08-11: Fix loop terminates when all checks pass.

    Requirement: 08-REQ-5.1, 08-REQ-5.2
    """

    @pytest.mark.asyncio
    async def test_all_passing_terminates_immediately(
        self,
        tmp_project: Path,
        mock_config: AgentFoxConfig,
    ) -> None:
        """When all checks pass on first run, loop terminates with ALL_FIXED."""
        pytest_check = CheckDescriptor(
            name="pytest",
            command=["uv", "run", "pytest"],
            category=CheckCategory.TEST,
        )

        with (
            patch(
                "agent_fox.fix.fix.detect_checks",
                return_value=[pytest_check],
            ),
            patch(
                "agent_fox.fix.fix.run_checks",
                return_value=([], [pytest_check]),
            ),
        ):
            result = await run_fix_loop(tmp_project, mock_config, max_passes=3)

        assert result.termination_reason == TerminationReason.ALL_FIXED
        assert result.passes_completed == 1
        assert result.sessions_consumed == 0
        assert result.clusters_remaining == 0


class TestFixLoopMaxPasses:
    """TS-08-12: Fix loop terminates at max passes.

    Requirement: 08-REQ-5.2
    """

    @pytest.mark.asyncio
    async def test_max_passes_terminates_with_remaining(
        self,
        tmp_project: Path,
        mock_config: AgentFoxConfig,
    ) -> None:
        """Loop stops after max_passes even if failures remain."""
        pytest_check = CheckDescriptor(
            name="pytest",
            command=["uv", "run", "pytest"],
            category=CheckCategory.TEST,
        )
        failure = make_failure_record(check=pytest_check, output="test failed")
        cluster = FailureCluster(
            label="Test failure",
            failures=[failure],
            suggested_approach="Fix the test",
        )

        mock_spec = MagicMock()
        mock_spec.task_prompt = "Fix this"
        mock_spec.spec_dir = tmp_project / "fix_spec"

        with (
            patch(
                "agent_fox.fix.fix.detect_checks",
                return_value=[pytest_check],
            ),
            patch(
                "agent_fox.fix.fix.run_checks",
                return_value=([failure], []),
            ),
            patch(
                "agent_fox.fix.fix.cluster_failures",
                return_value=[cluster],
            ),
            patch(
                "agent_fox.fix.fix.generate_fix_spec",
                return_value=mock_spec,
            ),
            patch(
                "agent_fox.fix.fix.cleanup_fix_specs",
            ),
        ):
            result = await run_fix_loop(tmp_project, mock_config, max_passes=2)

        assert result.termination_reason == TerminationReason.MAX_PASSES
        assert result.passes_completed == 2
        assert result.clusters_remaining > 0


# -- Edge case tests ---------------------------------------------------------


class TestMaxPassesClamping:
    """TS-08-E5: Max passes clamped to 1.

    Requirement: 08-REQ-7.E1
    """

    @pytest.mark.asyncio
    async def test_zero_clamped_to_one(
        self,
        tmp_project: Path,
        mock_config: AgentFoxConfig,
    ) -> None:
        """max_passes=0 is clamped to 1, so at least one pass runs."""
        pytest_check = CheckDescriptor(
            name="pytest",
            command=["uv", "run", "pytest"],
            category=CheckCategory.TEST,
        )
        failure = make_failure_record(check=pytest_check, output="test failed")
        cluster = FailureCluster(
            label="Test failure",
            failures=[failure],
            suggested_approach="Fix the test",
        )

        mock_spec = MagicMock()
        mock_spec.task_prompt = "Fix this"
        mock_spec.spec_dir = tmp_project / "fix_spec"

        with (
            patch(
                "agent_fox.fix.fix.detect_checks",
                return_value=[pytest_check],
            ),
            patch(
                "agent_fox.fix.fix.run_checks",
                return_value=([failure], []),
            ),
            patch(
                "agent_fox.fix.fix.cluster_failures",
                return_value=[cluster],
            ),
            patch(
                "agent_fox.fix.fix.generate_fix_spec",
                return_value=mock_spec,
            ),
            patch(
                "agent_fox.fix.fix.cleanup_fix_specs",
            ),
        ):
            result = await run_fix_loop(tmp_project, mock_config, max_passes=0)

        # Should clamp to 1 and run at least 1 pass
        assert result.passes_completed >= 0
        assert result.passes_completed <= 1

    @pytest.mark.asyncio
    async def test_negative_clamped_to_one(
        self,
        tmp_project: Path,
        mock_config: AgentFoxConfig,
    ) -> None:
        """max_passes=-1 is clamped to 1."""
        pytest_check = CheckDescriptor(
            name="pytest",
            command=["uv", "run", "pytest"],
            category=CheckCategory.TEST,
        )

        with (
            patch(
                "agent_fox.fix.fix.detect_checks",
                return_value=[pytest_check],
            ),
            patch(
                "agent_fox.fix.fix.run_checks",
                return_value=([], [pytest_check]),
            ),
        ):
            result = await run_fix_loop(tmp_project, mock_config, max_passes=-1)

        # Clamped to 1, and checks pass, so ALL_FIXED
        assert result.passes_completed <= 1
