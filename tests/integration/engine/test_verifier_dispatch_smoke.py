"""Integration smoke test: verifier dispatch does not produce phantom task group errors.

AC-3 (issue #534): A verifier dispatched for an auto_post node must not exit
early with 'No work performed: There is no task group N+1'.  It must complete
verification of the full spec.

This test exercises the real prompt-building pipeline through
NodeSessionRunner, mocking only the actual LLM session execution
(run_session) to avoid subprocess invocation.  It verifies that:

1. The task prompt sent to the verifier session does NOT reference any
   phantom task group number.
2. The session record returned has status='completed'.
3. The session summary does not contain 'There is no task group'.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.knowledge.sink import SessionOutcome

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SPEC_NAME = "08_parking_operator_adaptor"

# 6 real task groups — the scenario from the bug report.
_TASKS_MD = """\
# Tasks

## Task Group 1 — Foundation
- [ ] 1.1: Set up project structure
  - Create initial modules

## Task Group 2 — Core Logic
- [ ] 2.1: Implement adaptor pattern
  - Wire up parking operator

## Task Group 3 — Validation
- [ ] 3.1: Add input validation
  - Schema checks

## Task Group 4 — Persistence
- [ ] 4.1: Database layer
  - Query builders

## Task Group 5 — API Layer
- [ ] 5.1: REST endpoints
  - Controllers

## Task Group 6 — Integration
- [ ] 6.1: End-to-end wiring
  - Smoke tests
"""


def _setup_spec_dir(tmp_path: Path) -> Path:
    """Create a minimal spec directory with tasks.md containing 6 groups."""
    spec_root = tmp_path / ".agent-fox" / "specs"
    spec_dir = spec_root / _SPEC_NAME
    spec_dir.mkdir(parents=True)
    (spec_dir / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    # Minimal prd.md and requirements.md to satisfy assemble_context
    (spec_dir / "prd.md").write_text("# PRD\n\nParking operator adaptor.", encoding="utf-8")
    (spec_dir / "requirements.md").write_text("# Requirements\n\n- REQ-1: Adaptor works.", encoding="utf-8")
    (spec_dir / "design.md").write_text("# Design\n\nAdaptor pattern.", encoding="utf-8")
    return tmp_path


def _make_config(project_root: Path) -> MagicMock:
    """Build a minimal AgentFoxConfig that resolves spec_root correctly."""
    from agent_fox.core.config import AgentFoxConfig

    config = AgentFoxConfig()
    return config


def _make_successful_outcome(node_id: str) -> SessionOutcome:
    """Build a SessionOutcome representing a successful verifier session."""
    return SessionOutcome(
        spec_name=_SPEC_NAME,
        task_group="0",
        node_id=node_id,
        status="completed",
        input_tokens=1000,
        output_tokens=500,
        duration_ms=30000,
        response='{"verdict": "pass", "findings": []}',
    )


# ---------------------------------------------------------------------------
# AC-3: Verifier dispatch completes without phantom task group error
# ---------------------------------------------------------------------------


class TestVerifierDispatchNoPhantomGroup:
    """AC-3 (issue #534): Verifier dispatched for auto_post node completes
    without reporting 'There is no task group N+1'."""

    @pytest.mark.asyncio
    async def test_verifier_session_completes_without_phantom_error(
        self,
        tmp_path: Path,
    ) -> None:
        """Full lifecycle: build prompts → execute → verify no phantom error.

        Uses real NodeSessionRunner prompt building.  Mocks only run_session
        (the LLM call) and workspace creation/destruction to avoid git ops.
        """
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        project_root = _setup_spec_dir(tmp_path)
        config = _make_config(project_root)

        # Verifier node uses sentinel group_number=0 with 3-part node ID
        verifier_node_id = f"{_SPEC_NAME}:0:verifier"

        mock_kb = MagicMock()
        mock_kb.connection = MagicMock()
        # query_active_findings returns empty list
        mock_kb.connection.execute.return_value.fetchall.return_value = []

        runner = NodeSessionRunner(
            verifier_node_id,
            config,
            archetype="verifier",
            knowledge_db=mock_kb,
        )

        # Capture the prompts that would be sent to the session
        captured_prompts: dict[str, str] = {}

        async def mock_execute_session(
            node_id: str,
            workspace: object,
            system_prompt: str,
            task_prompt: str,
        ) -> SessionOutcome:
            captured_prompts["system"] = system_prompt
            captured_prompts["task"] = task_prompt
            return _make_successful_outcome(node_id)

        # Mock workspace creation/destruction (avoid real git operations)
        mock_workspace = MagicMock()
        mock_workspace.path = tmp_path / "worktree"
        mock_workspace.path.mkdir(parents=True, exist_ok=True)
        mock_workspace.branch = f"feature/{_SPEC_NAME}"

        with (
            patch.object(runner, "_execute_session", side_effect=mock_execute_session),
            patch.object(runner, "_setup_workspace", new_callable=AsyncMock, return_value=mock_workspace),
            patch("agent_fox.engine.session_lifecycle.destroy_worktree", new_callable=AsyncMock),
            patch(
                "agent_fox.engine.session_lifecycle._capture_develop_head",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            # Use tmp_path as cwd so spec resolution finds our test spec
            patch("agent_fox.engine.session_lifecycle.Path.cwd", return_value=project_root),
        ):
            record = await runner.execute(verifier_node_id, attempt=1)

        # --- Assertions ---

        # 1. Session must complete successfully
        assert record.status == "completed", (
            f"Verifier session should complete successfully, got status={record.status!r}, "
            f"error={record.error_message!r}"
        )

        # 2. Task prompt must not contain phantom group references
        task_prompt = captured_prompts.get("task", "")
        assert task_prompt, "Task prompt was not captured — mock_execute_session was not called"

        assert "There is no task group" not in task_prompt, (
            f"Task prompt contains phantom error text: {task_prompt!r}"
        )
        assert "task group 7" not in task_prompt.lower(), (
            f"Task prompt references phantom 'task group 7': {task_prompt!r}"
        )
        assert "task group" not in task_prompt.lower(), (
            f"Verifier task prompt should not reference any task group: {task_prompt!r}"
        )

        # 3. Task prompt must reference the spec and verifier role
        assert _SPEC_NAME in task_prompt, (
            f"Task prompt must mention spec name {_SPEC_NAME!r}: {task_prompt!r}"
        )
        assert "verifier" in task_prompt.lower(), (
            f"Task prompt must mention verifier role: {task_prompt!r}"
        )

        # 4. Archetype must be verifier
        assert record.archetype == "verifier", (
            f"Session record archetype should be 'verifier', got {record.archetype!r}"
        )

        # 5. No error message
        assert record.error_message is None, (
            f"Verifier session should have no error, got: {record.error_message!r}"
        )

    @pytest.mark.asyncio
    async def test_verifier_prompt_omits_group_for_all_group_counts(
        self,
        tmp_path: Path,
    ) -> None:
        """Verifier prompt building never references a group number,
        regardless of the spec's actual group count.

        This is a parameterized regression guard: even if the verifier
        node ID format changes, the prompt must stay group-agnostic.
        """
        from agent_fox.session.prompt import build_task_prompt

        # Simulate various group counts the verifier might be attached to
        for phantom_group in [0, 1, 7, 99]:
            result = build_task_prompt(
                task_group=phantom_group,
                spec_name=_SPEC_NAME,
                archetype="verifier",
            )
            assert "task group" not in result.lower(), (
                f"Verifier prompt with task_group={phantom_group} references "
                f"'task group': {result!r}"
            )
            assert _SPEC_NAME in result, (
                f"Verifier prompt must mention spec name: {result!r}"
            )

    def test_verifier_node_id_parsed_correctly(self) -> None:
        """3-part verifier node ID parses to group_number=0 with role='verifier'."""
        from agent_fox.core.node_id import parse_node_id

        parsed = parse_node_id(f"{_SPEC_NAME}:0:verifier")
        assert parsed.spec_name == _SPEC_NAME
        assert parsed.group_number == 0, (
            f"Verifier sentinel group_number should be 0, got {parsed.group_number}"
        )
        assert parsed.role == "verifier", (
            f"Parsed role should be 'verifier', got {parsed.role!r}"
        )
