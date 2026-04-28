"""Engine integration tests for knowledge system decoupling.

Test Spec: TS-114-8, TS-114-9, TS-114-11, TS-114-12, TS-114-16,
           TS-114-E3, TS-114-E4
Requirements: 114-REQ-2.4, 114-REQ-3.1, 114-REQ-3.3, 114-REQ-3.E1,
              114-REQ-4.1, 114-REQ-4.E1, 114-REQ-5.2
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agent_fox.knowledge.provider import KnowledgeProvider, NoOpKnowledgeProvider


def _make_mock_config() -> MagicMock:
    """Create a mock AgentFoxConfig that passes model tier resolution."""
    mock_config = MagicMock()
    mock_config.knowledge = MagicMock()
    mock_config.models = MagicMock()
    mock_config.orchestrator = MagicMock()
    # Ensure model tier resolution returns None so defaults are used
    mock_config.archetypes.overrides.get.return_value = None
    mock_config.archetypes.models = {}
    mock_config.models.coding = None
    mock_config.models.review = None
    return mock_config


# ---------------------------------------------------------------------------
# Mock KnowledgeProvider for tests
# ---------------------------------------------------------------------------


class MockKnowledgeProvider:
    """Mock provider that tracks calls for test assertions."""

    def __init__(self, retrieve_returns: list[str] | None = None) -> None:
        self.retrieve_called = False
        self.retrieve_args: tuple[str, str] | None = None
        self.retrieve_returns = retrieve_returns or []
        self.ingest_call_count = 0
        self.ingest_last_context: dict[str, Any] | None = None
        self.ingest_last_session_id: str | None = None
        self.ingest_last_spec_name: str | None = None

    def ingest(self, session_id: str, spec_name: str, context: dict[str, Any]) -> None:
        self.ingest_call_count += 1
        self.ingest_last_session_id = session_id
        self.ingest_last_spec_name = spec_name
        self.ingest_last_context = context

    def retrieve(
        self,
        spec_name: str,
        task_description: str,
        task_group: str | None = None,
        session_id: str | None = None,
    ) -> list[str]:
        self.retrieve_called = True
        self.retrieve_args = (spec_name, task_description)
        return self.retrieve_returns


# ---------------------------------------------------------------------------
# TS-114-8: Engine Uses NoOp as Default Provider
# ---------------------------------------------------------------------------


class TestDefaultProvider:
    """Verify engine infrastructure setup creates a KnowledgeProvider.

    Requirements: 114-REQ-2.4, 115-REQ-10.1, 115-REQ-10.2
    """

    def test_setup_infrastructure_returns_knowledge_provider(self) -> None:
        """_setup_infrastructure creates a FoxKnowledgeProvider (115-REQ-10.2
        supersedes the NoOpKnowledgeProvider default from 114-REQ-2.4)."""
        from agent_fox.engine.run import _setup_infrastructure
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        # Patch heavy dependencies to avoid real DB/sink creation
        with (
            patch("agent_fox.engine.run.open_knowledge_store") as mock_store,
            patch("agent_fox.engine.run.DuckDBSink"),
            patch("agent_fox.engine.run.SinkDispatcher"),
            patch("agent_fox.knowledge.agent_trace.AgentTraceSink"),
        ):
            mock_db = MagicMock()
            mock_db.connection = MagicMock()
            mock_store.return_value = mock_db

            mock_config = MagicMock()
            mock_config.knowledge = MagicMock()
            mock_config.knowledge.store_path = ":memory:"

            infra = _setup_infrastructure(mock_config)

        assert "knowledge_provider" in infra
        assert isinstance(infra["knowledge_provider"], KnowledgeProvider)
        assert isinstance(infra["knowledge_provider"], FoxKnowledgeProvider)


# ---------------------------------------------------------------------------
# TS-114-9: Engine Calls retrieve() Pre-Session
# ---------------------------------------------------------------------------


class TestRetrieveCalled:
    """Verify _build_prompts calls knowledge_provider.retrieve().

    Requirements: 114-REQ-3.1
    """

    def test_retrieve_called_during_prompt_assembly(self) -> None:
        """_build_prompts calls provider.retrieve() with (spec_name, task_description)."""
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        mock_provider = MockKnowledgeProvider(retrieve_returns=["fact block 1"])

        mock_config = _make_mock_config()
        mock_db = MagicMock()

        runner = NodeSessionRunner(
            "spec_01:1",
            mock_config,
            knowledge_db=mock_db,
            knowledge_provider=mock_provider,
            sink_dispatcher=MagicMock(),
        )

        # Patch internal helpers inside _build_prompts (NOT _build_prompts itself)
        # so the real _build_prompts runs and calls provider.retrieve()
        with (
            patch("agent_fox.engine.session_lifecycle.assemble_context", return_value=MagicMock()),
            patch("agent_fox.engine.session_lifecycle.build_system_prompt", return_value="sys"),
            patch("agent_fox.engine.session_lifecycle.build_task_prompt", return_value="task"),
            patch("agent_fox.core.config.resolve_spec_root", return_value=MagicMock()),
        ):
            runner._build_prompts("/tmp/repo", 1, None)

        assert mock_provider.retrieve_called
        assert mock_provider.retrieve_args is not None
        assert mock_provider.retrieve_args[0] == "spec_01"


# ---------------------------------------------------------------------------
# TS-114-11: Empty Retrieve Means No Knowledge Context
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TS-114-16: Barrier Still Runs Retained Operational Steps
# ---------------------------------------------------------------------------


class TestBarrierRetainedSteps:
    """Verify run_sync_barrier_sequence still executes operational steps.

    Retained: worktree verification, develop sync, hot-load, barrier callback.
    Removed: consolidation, compaction, lifecycle cleanup, sleep compute, rendering.

    Requirements: 114-REQ-5.2
    """

    @pytest.mark.asyncio
    async def test_barrier_runs_operational_steps(self) -> None:
        """run_sync_barrier_sequence calls all retained operational steps."""
        from unittest.mock import AsyncMock as AM

        from agent_fox.engine.barrier import run_sync_barrier_sequence

        mock_state = MagicMock()
        mock_state.node_states = {"spec_01:1": "completed"}

        mock_emit_audit = MagicMock()
        mock_hot_load = AM()
        mock_sync_plan = MagicMock()
        mock_reload = MagicMock()

        with (
            patch(
                "agent_fox.engine.barrier.verify_worktrees",
                return_value=[],
            ) as mock_verify,
            patch(
                "agent_fox.engine.barrier.sync_develop_bidirectional",
                new_callable=AM,
            ) as mock_sync,
        ):
            await run_sync_barrier_sequence(
                state=mock_state,
                sync_interval=1,
                repo_root=MagicMock(),
                emit_audit=mock_emit_audit,
                specs_dir=MagicMock(),
                hot_load_enabled=True,
                hot_load_fn=mock_hot_load,
                sync_plan_fn=mock_sync_plan,
                barrier_callback=None,
                reload_config_fn=mock_reload,
            )

        mock_verify.assert_called_once()
        mock_sync.assert_called_once()
        mock_hot_load.assert_called_once()
        mock_reload.assert_called_once()
        mock_emit_audit.assert_called_once()


class TestEmptyRetrieve:
    """Verify engine proceeds without knowledge context when provider returns [].

    Requirements: 114-REQ-3.3
    """

    def test_empty_retrieve_produces_valid_prompts(self) -> None:
        """When provider.retrieve() returns [], session proceeds without crash."""
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        mock_config = _make_mock_config()
        mock_db = MagicMock()

        noop = NoOpKnowledgeProvider()
        runner = NodeSessionRunner(
            "spec_01:1",
            mock_config,
            knowledge_db=mock_db,
            knowledge_provider=noop,
            sink_dispatcher=MagicMock(),
        )

        # Mock the prompt assembly functions to isolate provider behavior
        with (
            patch("agent_fox.engine.session_lifecycle.assemble_context", return_value=MagicMock()),
            patch("agent_fox.engine.session_lifecycle.build_system_prompt", return_value="sys"),
            patch("agent_fox.engine.session_lifecycle.build_task_prompt", return_value="task"),
            patch("agent_fox.core.config.resolve_spec_root", return_value=MagicMock()),
        ):
            sys_prompt, task_prompt = runner._build_prompts("/tmp/repo", 1, None)

        assert isinstance(sys_prompt, str)
        assert len(sys_prompt) > 0


# ---------------------------------------------------------------------------
# TS-114-12: Engine Calls ingest() Post-Session
# ---------------------------------------------------------------------------


class TestIngestCalled:
    """Verify _ingest_knowledge calls provider.ingest() once with correct args.

    Requirements: 114-REQ-4.1
    """

    def test_ingest_called_with_correct_context(self) -> None:
        """_ingest_knowledge calls provider.ingest() with session metadata."""
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        mock_provider = MockKnowledgeProvider()
        mock_config = _make_mock_config()
        mock_db = MagicMock()

        runner = NodeSessionRunner(
            "spec_01:1",
            mock_config,
            knowledge_db=mock_db,
            knowledge_provider=mock_provider,
            sink_dispatcher=MagicMock(),
        )

        runner._ingest_knowledge(
            "spec_01:1",
            ["src/foo.py"],
            "abc123",
            "completed",
        )

        assert mock_provider.ingest_call_count == 1
        ctx = mock_provider.ingest_last_context
        assert ctx is not None
        assert "touched_files" in ctx
        assert "commit_sha" in ctx
        assert "session_status" in ctx


# ---------------------------------------------------------------------------
# TS-114-E3: Retrieve Exception Handled Gracefully
# ---------------------------------------------------------------------------


class TestRetrieveException:
    """Verify engine handles retrieve() exceptions gracefully.

    Requirements: 114-REQ-3.E1
    """

    def test_retrieve_failure_logs_warning_and_proceeds(self, caplog: pytest.LogCaptureFixture) -> None:
        """When retrieve() raises, engine logs WARNING and uses empty context."""

        class FailingProvider:
            def ingest(self, session_id: str, spec_name: str, context: dict[str, Any]) -> None:
                pass

            def retrieve(self, spec_name: str, task_description: str) -> list[str]:
                raise RuntimeError("broken")

        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        mock_config = _make_mock_config()
        mock_db = MagicMock()

        runner = NodeSessionRunner(
            "spec_01:1",
            mock_config,
            knowledge_db=mock_db,
            knowledge_provider=FailingProvider(),
            sink_dispatcher=MagicMock(),
        )

        with (
            patch("agent_fox.engine.session_lifecycle.assemble_context", return_value=MagicMock()),
            patch("agent_fox.engine.session_lifecycle.build_system_prompt", return_value="sys"),
            patch("agent_fox.engine.session_lifecycle.build_task_prompt", return_value="task"),
            patch("agent_fox.core.config.resolve_spec_root", return_value=MagicMock()),
            caplog.at_level(logging.WARNING),
        ):
            sys_prompt, task_prompt = runner._build_prompts("/tmp/repo", 1, None)

        assert isinstance(sys_prompt, str)
        # Check that a warning was logged about retrieve failure
        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("retrieve" in msg.lower() or "knowledge" in msg.lower() for msg in warning_messages)


# ---------------------------------------------------------------------------
# TS-114-E4: Ingest Exception Handled Gracefully
# ---------------------------------------------------------------------------


class TestIngestException:
    """Verify engine handles ingest() exceptions gracefully.

    Requirements: 114-REQ-4.E1
    """

    def test_ingest_failure_logs_warning_and_continues(self, caplog: pytest.LogCaptureFixture) -> None:
        """When ingest() raises, engine logs WARNING and does not retry."""

        class FailingProvider:
            ingest_count = 0

            def ingest(self, session_id: str, spec_name: str, context: dict[str, Any]) -> None:
                FailingProvider.ingest_count += 1
                raise RuntimeError("broken")

            def retrieve(self, spec_name: str, task_description: str) -> list[str]:
                return []

        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        provider = FailingProvider()
        mock_config = _make_mock_config()
        mock_db = MagicMock()

        runner = NodeSessionRunner(
            "spec_01:1",
            mock_config,
            knowledge_db=mock_db,
            knowledge_provider=provider,
            sink_dispatcher=MagicMock(),
        )

        with caplog.at_level(logging.WARNING):
            # Should not raise
            runner._ingest_knowledge("node_1", ["f.py"], "sha", "completed")

        assert provider.ingest_count == 1  # called once, no retry
        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("ingest" in msg.lower() or "knowledge" in msg.lower() for msg in warning_messages)
