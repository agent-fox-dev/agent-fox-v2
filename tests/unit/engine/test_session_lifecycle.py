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

from agent_fox.knowledge.sink import SessionOutcome

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

    def test_default_coder_uses_global_models_coding(self) -> None:
        """Coder archetype uses config.models.coding (default ADVANCED)."""
        runner = NodeSessionRunner("spec:1", AgentFoxConfig(), knowledge_db=_MOCK_KB)
        assert runner._resolved_model_id == "claude-opus-4-6"

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
        """Valid session-summary.json is parsed and returned."""
        summary = {"summary": "Did things", "tests_added_or_modified": []}
        (tmp_path / ".agent-fox").mkdir()
        (tmp_path / ".agent-fox" / "session-summary.json").write_text(json.dumps(summary))
        workspace = WorkspaceInfo(path=tmp_path, spec_name="s", task_group=1, branch="feature/s/1")
        result = NodeSessionRunner._read_session_artifacts(workspace)
        assert result == summary

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        """Returns None when .session-summary.json does not exist."""
        workspace = WorkspaceInfo(path=tmp_path, spec_name="s", task_group=1, branch="feature/s/1")
        assert NodeSessionRunner._read_session_artifacts(workspace) is None

    def test_returns_none_on_invalid_json(self, tmp_path: Path) -> None:
        """Returns None when session-summary.json contains invalid JSON."""
        (tmp_path / ".agent-fox").mkdir(exist_ok=True)
        (tmp_path / ".agent-fox" / "session-summary.json").write_text("not valid json {{{")
        workspace = WorkspaceInfo(path=tmp_path, spec_name="s", task_group=1, branch="feature/s/1")
        assert NodeSessionRunner._read_session_artifacts(workspace) is None


class TestCleanupSessionArtifacts:
    """Tests for NodeSessionRunner._cleanup_session_artifacts."""

    def test_deletes_summary_file(self, tmp_path: Path) -> None:
        """Cleanup removes session-summary.json."""
        (tmp_path / ".agent-fox").mkdir()
        summary_path = tmp_path / ".agent-fox" / "session-summary.json"
        summary_path.write_text('{"summary": "done"}')
        workspace = WorkspaceInfo(path=tmp_path, spec_name="s", task_group=1, branch="feature/s/1")
        NodeSessionRunner._cleanup_session_artifacts(workspace)
        assert not summary_path.exists()

    def test_noop_when_missing(self, tmp_path: Path) -> None:
        """Cleanup is a no-op when the file does not exist."""
        workspace = WorkspaceInfo(path=tmp_path, spec_name="s", task_group=1, branch="feature/s/1")
        NodeSessionRunner._cleanup_session_artifacts(workspace)  # should not raise


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


# ---------------------------------------------------------------------------
# Regression: no duplicate session_outcomes rows (fixes #473)
# ---------------------------------------------------------------------------


class TestNoDuplicateSessionOutcomeWrite:
    """Verify _run_and_harvest does not write session outcomes to the sink.

    Session outcomes are written exclusively by SessionResultHandler.process()
    via state.record_session(). The old sink-based path caused duplicate rows
    in the session_outcomes table (issue #473).
    """

    @pytest.mark.asyncio
    async def test_run_and_harvest_does_not_call_sink_record_session_outcome(self) -> None:
        """_run_and_harvest must not dispatch record_session_outcome to sinks."""
        config = AgentFoxConfig()
        sink = MagicMock()
        sink.record_session_outcome = MagicMock()

        runner = NodeSessionRunner(
            "spec:1",
            config,
            knowledge_db=_MOCK_KB,
            sink_dispatcher=sink,
        )

        workspace = WorkspaceInfo(
            path=Path("/tmp/ws"),
            spec_name="spec",
            task_group=1,
            branch="feature/spec/1",
        )

        fake_outcome = SessionOutcome(
            spec_name="spec",
            task_group="1",
            node_id="spec:1",
            status="completed",
            input_tokens=100,
            output_tokens=200,
            duration_ms=5000,
        )

        with (
            patch.object(
                runner,
                "_execute_session",
                new_callable=AsyncMock,
                return_value=fake_outcome,
            ),
            patch.object(
                runner,
                "_harvest_and_integrate",
                new_callable=AsyncMock,
                return_value=("completed", None, []),
            ),
            patch(
                "agent_fox.engine.session_lifecycle._capture_develop_head",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "agent_fox.engine.session_lifecycle.emit_audit_event",
            ),
            patch.object(
                runner,
                "_extract_knowledge_and_findings",
                new_callable=AsyncMock,
            ),
        ):
            record = await runner._run_and_harvest(
                "spec:1", 1, workspace, "sys", "task", Path("/tmp"),
            )

        assert record.status == "completed"
        sink.record_session_outcome.assert_not_called()
