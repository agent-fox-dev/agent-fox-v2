"""Unit tests for engine/session_lifecycle.py helper methods.

Tests for NodeSessionRunner helper methods and error handling that
are not covered by the knowledge-wiring integration tests.

Requirements: 16-REQ-5.1, 16-REQ-5.E1, 26-REQ-4.4, 26-REQ-3.4
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig
from agent_fox.engine.sdk_params import clamp_instances
from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.workspace import WorkspaceInfo

_MOCK_KB = MagicMock(spec=KnowledgeDB)

# ---------------------------------------------------------------------------
# _clamp_instances
# ---------------------------------------------------------------------------


class TestClampInstances:
    """Tests for the _clamp_instances helper."""

    def test_coder_clamped_to_one(self) -> None:
        assert clamp_instances("coder", 3) == 1

    def test_coder_one_unchanged(self) -> None:
        assert clamp_instances("coder", 1) == 1

    def test_non_coder_max_five(self) -> None:
        assert clamp_instances("reviewer", 10) == 5

    def test_non_coder_min_one(self) -> None:
        assert clamp_instances("verifier", 0) == 1

    def test_valid_value_unchanged(self) -> None:
        assert clamp_instances("reviewer", 3) == 3


# ---------------------------------------------------------------------------
# _resolve_model_tier
# ---------------------------------------------------------------------------


class TestResolveModelTier:
    """Tests for NodeSessionRunner._resolve_model_tier."""

    def test_default_coder_uses_standard(self) -> None:
        """Coder archetype defaults to STANDARD from the registry."""
        runner = NodeSessionRunner("spec:1", AgentFoxConfig(), knowledge_db=_MOCK_KB)
        assert runner._resolved_model_id == "claude-sonnet-4-6"

    def test_config_override_takes_priority(self) -> None:
        """Config override in archetypes.models takes priority over registry."""
        config = AgentFoxConfig(archetypes=ArchetypesConfig(models={"coder": "SIMPLE"}))
        runner = NodeSessionRunner("spec:1", config, knowledge_db=_MOCK_KB)
        assert runner._resolved_model_id == "claude-haiku-4-5"

    def test_reviewer_defaults_to_standard(self) -> None:
        """Reviewer archetype defaults to STANDARD from the registry."""
        runner = NodeSessionRunner("spec:1", AgentFoxConfig(), archetype="reviewer", knowledge_db=_MOCK_KB)
        assert runner._resolved_model_id == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# _resolve_security_config
# ---------------------------------------------------------------------------


class TestResolveSecurityConfig:
    """Tests for NodeSessionRunner._resolve_security_config."""

    def test_coder_returns_none_for_global(self) -> None:
        """Coder has no default allowlist, returns None (use global)."""
        runner = NodeSessionRunner("spec:1", AgentFoxConfig(), knowledge_db=_MOCK_KB)
        assert runner._resolved_security is None

    def test_maintainer_hunt_returns_default_allowlist(self) -> None:
        """maintainer:hunt has a default allowlist from the registry (replaces triage)."""
        runner = NodeSessionRunner(
            "spec:1", AgentFoxConfig(), archetype="maintainer", mode="hunt", knowledge_db=_MOCK_KB
        )
        assert runner._resolved_security is not None
        assert runner._resolved_security.bash_allowlist is not None
        assert "ls" in runner._resolved_security.bash_allowlist
        assert "git" in runner._resolved_security.bash_allowlist

    def test_config_allowlist_overrides_registry(self) -> None:
        """Config allowlist override takes priority over registry default."""
        config = AgentFoxConfig(archetypes=ArchetypesConfig(allowlists={"maintainer": ["echo", "pwd"]}))
        runner = NodeSessionRunner("spec:1", config, archetype="maintainer", mode="hunt", knowledge_db=_MOCK_KB)
        assert runner._resolved_security is not None
        assert runner._resolved_security.bash_allowlist == ["echo", "pwd"]


# ---------------------------------------------------------------------------
# _read_session_artifacts
# ---------------------------------------------------------------------------


class TestReadSessionArtifacts:
    """Tests for NodeSessionRunner._read_session_artifacts."""

    def test_returns_parsed_json(self, tmp_path: Path) -> None:
        """Valid .session-summary.json is parsed and returned."""
        summary = {"summary": "Did things", "tests_added_or_modified": []}
        (tmp_path / ".session-summary.json").write_text(json.dumps(summary))
        workspace = WorkspaceInfo(path=tmp_path, spec_name="s", task_group=1, branch="feature/s/1")
        result = NodeSessionRunner._read_session_artifacts(workspace)
        assert result == summary

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        """Returns None when .session-summary.json does not exist."""
        workspace = WorkspaceInfo(path=tmp_path, spec_name="s", task_group=1, branch="feature/s/1")
        assert NodeSessionRunner._read_session_artifacts(workspace) is None

    def test_returns_none_on_invalid_json(self, tmp_path: Path) -> None:
        """Returns None when .session-summary.json contains invalid JSON."""
        (tmp_path / ".session-summary.json").write_text("not valid json {{{")
        workspace = WorkspaceInfo(path=tmp_path, spec_name="s", task_group=1, branch="feature/s/1")
        assert NodeSessionRunner._read_session_artifacts(workspace) is None


# ---------------------------------------------------------------------------
# execute() error handling — 16-REQ-5.E1
# ---------------------------------------------------------------------------


class TestExecuteErrorHandling:
    """Verify execute() catches exceptions and returns a failed SessionRecord."""

    @pytest.mark.asyncio
    async def test_worktree_creation_failure_returns_failed_record(self) -> None:
        """If create_worktree raises, a failed SessionRecord is returned."""
        config = AgentFoxConfig()
        runner = NodeSessionRunner("spec:1", config, knowledge_db=_MOCK_KB)

        with (
            patch(
                "agent_fox.engine.session_lifecycle.ensure_develop",
                new_callable=AsyncMock,
            ),
            patch(
                "agent_fox.engine.session_lifecycle.create_worktree",
                new_callable=AsyncMock,
                side_effect=RuntimeError("worktree failed"),
            ),
        ):
            record = await runner.execute("spec:1", 1)

        assert record.status == "failed"
        assert record.error_message is not None
        assert "worktree failed" in record.error_message

    @pytest.mark.asyncio
    async def test_retry_prompt_includes_previous_error(self) -> None:
        """On retry (attempt > 1), the task prompt includes the previous error."""
        config = AgentFoxConfig()
        runner = NodeSessionRunner("spec:1", config, knowledge_db=_MOCK_KB)

        workspace = WorkspaceInfo(
            path=Path("/tmp/ws"),
            spec_name="spec",
            task_group=1,
            branch="feature/spec/1",
        )

        captured_prompts: dict = {}

        async def _fake_run_and_harvest(node_id, attempt, workspace, system_prompt, task_prompt, repo_root):
            captured_prompts["task"] = task_prompt
            from datetime import UTC, datetime

            from agent_fox.engine.state import SessionRecord

            return SessionRecord(
                node_id=node_id,
                attempt=attempt,
                status="completed",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                duration_ms=0,
                error_message=None,
                timestamp=datetime.now(UTC).isoformat(),
            )

        with (
            patch(
                "agent_fox.engine.session_lifecycle.ensure_develop",
                new_callable=AsyncMock,
            ),
            patch(
                "agent_fox.engine.session_lifecycle.create_worktree",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch(
                "agent_fox.engine.session_lifecycle.destroy_worktree",
                new_callable=AsyncMock,
            ),
            patch.object(runner, "_run_and_harvest", _fake_run_and_harvest),
            patch(
                "agent_fox.engine.session_lifecycle.assemble_context",
                return_value="context",
            ),
        ):
            await runner.execute("spec:1", 2, previous_error="type error in foo")

        assert "type error in foo" in captured_prompts["task"]
        assert "retry attempt 2" in captured_prompts["task"].lower()
