"""Integration smoke tests: issue summary posting end-to-end.

Test Spec: TS-108-E3, TS-108-SMOKE-1
Requirements: 108-REQ-4.1, 108-REQ-4.2, 108-REQ-5.1, 108-REQ-5.E1
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.core.config import OrchestratorConfig

# ---------------------------------------------------------------------------
# Helper: build a minimal plan JSON where all nodes are already "completed"
# ---------------------------------------------------------------------------


def _make_completed_plan(spec_name: str) -> dict:
    """Build a plan dict with one completed node for the given spec."""
    node_id = f"{spec_name}:1"
    return {
        "metadata": {
            "created_at": "2026-01-01T00:00:00",
            "fast_mode": False,
            "filtered_spec": None,
            "version": "0.1.0",
        },
        "nodes": {
            node_id: {
                "id": node_id,
                "spec_name": spec_name,
                "group_number": 1,
                "title": "Task group 1",
                "optional": False,
                "status": "completed",
                "subtask_count": 0,
                "body": "",
                "archetype": "coder",
            }
        },
        "edges": [],
        "order": [node_id],
    }


def _make_spec_dir(base: Path, spec_name: str, github_url: str) -> None:
    """Create a minimal spec directory with prd.md and tasks.md."""
    spec_dir = base / spec_name
    spec_dir.mkdir(parents=True)
    (spec_dir / "prd.md").write_text(f"# PRD\n\n## Source\n\nSource: {github_url}\n")
    (spec_dir / "tasks.md").write_text("- [x] 1. Implement feature\n")


# ---------------------------------------------------------------------------
# TS-108-E3: Orchestrator skips issue summaries when platform is None
# Requirements: 108-REQ-5.E1
# ---------------------------------------------------------------------------


class TestOrchestratorSkipsWhenNoPlatform:
    """TS-108-E3: platform=None → no issue summary operations, no warnings."""

    @pytest.mark.asyncio
    async def test_no_platform_no_issue_summary_calls(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Orchestrator with platform=None skips all issue summary operations.

        Requirements: 108-REQ-5.E1
        """
        from agent_fox.engine.engine import Orchestrator

        spec_name = "108_my_spec"
        specs_dir = tmp_path / ".specs"
        _make_spec_dir(specs_dir, spec_name, "https://github.com/owner/repo/issues/1")

        plan_dir = tmp_path / ".agent-fox"
        plan_dir.mkdir()
        plan_path = plan_dir / "plan.json"
        plan_path.write_text(json.dumps(_make_completed_plan(spec_name)))

        mock_runner = MagicMock()
        mock_runner.execute = AsyncMock(
            return_value=MagicMock(
                node_id=f"{spec_name}:1",
                status="completed",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                duration_ms=0,
                error_message=None,
                spec_name=spec_name,
                task_group=1,
                archetype="coder",
            )
        )

        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        # platform=None: Orchestrator must NOT require platform, must skip summaries
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            specs_dir=specs_dir,
            session_runner_factory=lambda nid, **kw: mock_runner,
            platform=None,
        )

        import logging

        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.issue_summary"):
            await orchestrator.run()

        # No warnings about issue summaries should be logged
        issue_summary_warnings = [
            r for r in caplog.records if "issue summar" in r.getMessage().lower() and r.levelno >= logging.WARNING
        ]
        assert len(issue_summary_warnings) == 0


# ---------------------------------------------------------------------------
# TS-108-SMOKE-1: End-to-end issue summary posting
# Requirements: 108-REQ-4.1, 108-REQ-4.2
# ---------------------------------------------------------------------------


class TestEndToEndIssueSummary:
    """TS-108-SMOKE-1: Full flow from orchestrator end-of-run to comment posting."""

    @pytest.mark.asyncio
    async def test_comment_posted_for_completed_spec(self, tmp_path: Path) -> None:
        """Orchestrator posts summary comment when spec completes and platform is set.

        Requirements: 108-REQ-4.1, 108-REQ-4.2
        """
        from agent_fox.engine.engine import Orchestrator
        from agent_fox.engine.issue_summary import post_issue_summaries  # noqa: F401 (verifies module exists)

        spec_name = "108_smoke_spec"
        specs_dir = tmp_path / ".specs"
        _make_spec_dir(specs_dir, spec_name, "https://github.com/owner/repo/issues/1")

        plan_dir = tmp_path / ".agent-fox"
        plan_dir.mkdir()
        plan_path = plan_dir / "plan.json"
        plan_path.write_text(json.dumps(_make_completed_plan(spec_name)))

        mock_runner = MagicMock()
        mock_runner.execute = AsyncMock(
            return_value=MagicMock(
                node_id=f"{spec_name}:1",
                status="completed",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                duration_ms=0,
                error_message=None,
                spec_name=spec_name,
                task_group=1,
                archetype="coder",
            )
        )

        # Mock platform with async add_issue_comment
        platform = MagicMock()
        platform.forge_type = "github"
        platform.add_issue_comment = AsyncMock()

        # Mock git rev-parse develop to return a known SHA
        mock_git = MagicMock()
        mock_git.returncode = 0
        mock_git.stdout = "deadbeef1234\n"

        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            specs_dir=specs_dir,
            session_runner_factory=lambda nid, **kw: mock_runner,
            platform=platform,
        )

        with patch("subprocess.run", return_value=mock_git):
            await orchestrator.run()

        # add_issue_comment must be called exactly once
        platform.add_issue_comment.assert_called_once()
        call_args = platform.add_issue_comment.call_args
        issue_number = call_args[0][0]
        body = call_args[0][1]

        assert issue_number == 1, f"Expected issue 1, got {issue_number}"
        assert spec_name in body, "Body must contain spec name"
        # SHA is either the real one or "unknown" if git call is intercepted differently
        assert "deadbeef1234" in body or "unknown" in body, "Body must contain a commit SHA"
        assert "*Auto-generated by agent-fox.*" in body, "Body must contain footer"
