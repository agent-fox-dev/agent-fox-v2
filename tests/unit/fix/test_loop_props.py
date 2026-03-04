"""Property tests for fix loop.

Test Spec: TS-08-P4 (loop termination bound)
Property: Property 4 from design.md
Requirements: 08-REQ-5.1, 08-REQ-5.2
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.clusterer import FailureCluster
from agent_fox.fix.collector import FailureRecord
from agent_fox.fix.detector import CheckCategory, CheckDescriptor
from agent_fox.fix.loop import run_fix_loop


class TestLoopTerminationBound:
    """TS-08-P4: Loop termination bound.

    Property 4: For any max_passes >= 1, the fix loop never exceeds
    max_passes iterations.
    """

    @given(max_passes=st.integers(min_value=1, max_value=5))
    @settings(max_examples=10, deadline=None)
    @pytest.mark.asyncio
    async def test_passes_never_exceed_max(
        self,
        max_passes: int,
        tmp_path_factory,
    ) -> None:
        """passes_completed is always <= max_passes."""
        tmp_dir = tmp_path_factory.mktemp("loop")
        config = AgentFoxConfig()

        pytest_check = CheckDescriptor(
            name="pytest",
            command=["uv", "run", "pytest"],
            category=CheckCategory.TEST,
        )
        failure = FailureRecord(
            check=pytest_check,
            output="test failed",
            exit_code=1,
        )
        cluster = FailureCluster(
            label="Test failure",
            failures=[failure],
            suggested_approach="Fix it",
        )

        mock_spec = MagicMock()
        mock_spec.task_prompt = "Fix this"
        mock_spec.spec_dir = tmp_dir / "fix_spec"

        with (
            patch(
                "agent_fox.fix.loop.detect_checks",
                return_value=[pytest_check],
            ),
            patch(
                "agent_fox.fix.loop.run_checks",
                return_value=([failure], []),
            ),
            patch(
                "agent_fox.fix.loop.cluster_failures",
                return_value=[cluster],
            ),
            patch(
                "agent_fox.fix.loop.generate_fix_spec",
                return_value=mock_spec,
            ),
            patch(
                "agent_fox.fix.loop.cleanup_fix_specs",
            ),
        ):
            result = await run_fix_loop(tmp_dir, config, max_passes=max_passes)

        assert result.passes_completed <= max_passes
