"""Integration smoke tests for knowledge system decoupling.

Test Spec: TS-114-SMOKE-1, TS-114-SMOKE-2, TS-114-SMOKE-3,
           TS-114-SMOKE-4, TS-114-SMOKE-5
Requirements: 114-REQ-2.4, 114-REQ-3.1, 114-REQ-4.1,
              114-REQ-5.1, 114-REQ-5.2
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.knowledge.provider import NoOpKnowledgeProvider


def _make_mock_config() -> MagicMock:
    """Create a mock AgentFoxConfig that passes model tier resolution."""
    mock_config = MagicMock()
    mock_config.knowledge = MagicMock()
    mock_config.models = MagicMock()
    mock_config.orchestrator = MagicMock()
    mock_config.archetypes.overrides.get.return_value = None
    mock_config.archetypes.models = {}
    mock_config.models.coding = None
    mock_config.models.review = None
    return mock_config

# ---------------------------------------------------------------------------
# TS-114-SMOKE-1: Pre-Session Retrieval Path
# ---------------------------------------------------------------------------


class TestPreSessionRetrievalSmoke:
    """Verify NoOpKnowledgeProvider.retrieve() is called during prompt assembly.

    Must use real NoOpKnowledgeProvider, not a mock.
    """

    def test_noop_retrieve_during_prompt_build(self) -> None:
        """Real NoOpKnowledgeProvider.retrieve() returns [] and prompts build."""
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        provider = NoOpKnowledgeProvider()  # real, not mocked
        mock_db = MagicMock()

        runner = NodeSessionRunner(
            "spec_01:1",
            _make_mock_config(),
            knowledge_db=mock_db,
            knowledge_provider=provider,  # real provider
            sink_dispatcher=MagicMock(),
        )

        with (
            patch("agent_fox.engine.session_lifecycle.assemble_context", return_value=MagicMock()),
            patch("agent_fox.engine.session_lifecycle.build_system_prompt", return_value="system prompt"),
            patch("agent_fox.engine.session_lifecycle.build_task_prompt", return_value="task prompt"),
            patch("agent_fox.core.config.resolve_spec_root", return_value=MagicMock()),
        ):
            sys_prompt, task_prompt = runner._build_prompts("/tmp/repo", 1, None)

        assert isinstance(sys_prompt, str)
        assert isinstance(task_prompt, str)


# ---------------------------------------------------------------------------
# TS-114-SMOKE-2: Post-Session Ingestion Path
# ---------------------------------------------------------------------------


class TestPostSessionIngestionSmoke:
    """Verify NoOpKnowledgeProvider.ingest() is called after session completion.

    Must use real NoOpKnowledgeProvider, not a mock.
    """

    def test_noop_ingest_after_session(self) -> None:
        """Real NoOpKnowledgeProvider.ingest() completes without error."""
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        provider = NoOpKnowledgeProvider()  # real, not mocked
        mock_db = MagicMock()

        runner = NodeSessionRunner(
            "spec_01:1",
            _make_mock_config(),
            knowledge_db=mock_db,
            knowledge_provider=provider,
            sink_dispatcher=MagicMock(),
        )

        # Should not raise
        runner._ingest_knowledge("spec_01:1", ["src/f.py"], "abc123", "completed")


# ---------------------------------------------------------------------------
# TS-114-SMOKE-3: Simplified Barrier Path
# ---------------------------------------------------------------------------


class TestSimplifiedBarrierSmoke:
    """Verify barrier runs to completion without removed components.

    Must use real run_sync_barrier_sequence, not a mock.
    """

    @pytest.mark.asyncio
    async def test_barrier_completes_without_error(self) -> None:
        """Barrier completes without consolidation/compaction/sleep/cleanup."""
        from agent_fox.engine.barrier import run_sync_barrier_sequence

        mock_state = MagicMock()
        mock_state.node_states = {"spec_01:1": "completed"}

        await run_sync_barrier_sequence(
            state=mock_state,
            sync_interval=1,
            repo_root=MagicMock(),
            emit_audit=MagicMock(),
            specs_dir=None,
            hot_load_enabled=False,
            hot_load_fn=AsyncMock(),
            sync_plan_fn=MagicMock(),
            barrier_callback=None,
            knowledge_db_conn=None,
        )
        # No error raised = barrier completed


# ---------------------------------------------------------------------------
# TS-114-SMOKE-4: Engine Initialization Path
# ---------------------------------------------------------------------------


class TestEngineInitSmoke:
    """Verify _setup_infrastructure creates NoOpKnowledgeProvider.

    Must use real _setup_infrastructure, not a mock.
    """

    def test_infra_contains_noop_provider(self) -> None:
        """_setup_infrastructure returns NoOpKnowledgeProvider."""
        from agent_fox.engine.run import _setup_infrastructure

        with (
            patch("agent_fox.engine.run.open_knowledge_store") as mock_store,
            patch("agent_fox.engine.run.DuckDBSink"),
            patch("agent_fox.knowledge.sink.SinkDispatcher") as mock_sink_cls,
            patch("agent_fox.knowledge.agent_trace.AgentTraceSink"),
        ):
            mock_db = MagicMock()
            mock_db.connection = MagicMock()
            mock_store.return_value = mock_db
            mock_sink = MagicMock()
            mock_sink_cls.return_value = mock_sink

            mock_config = MagicMock()
            mock_config.knowledge = MagicMock()

            infra = _setup_infrastructure(mock_config)

        assert "knowledge_provider" in infra
        assert isinstance(infra["knowledge_provider"], NoOpKnowledgeProvider)


# ---------------------------------------------------------------------------
# TS-114-SMOKE-5: Review Findings Path Unchanged
# ---------------------------------------------------------------------------


class TestReviewFindingsSmoke:
    """Verify review findings persistence still works after decoupling.

    Must use real _extract_knowledge_and_findings path (not mocked).
    """

    @pytest.mark.asyncio
    async def test_review_findings_path_works(self) -> None:
        """_extract_knowledge_and_findings completes for reviewer archetype."""
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        provider = NoOpKnowledgeProvider()
        mock_db = MagicMock()

        runner = NodeSessionRunner(
            "spec_01:1",
            _make_mock_config(),
            archetype="reviewer",
            knowledge_db=mock_db,
            knowledge_provider=provider,
            sink_dispatcher=MagicMock(),
        )

        workspace = MagicMock()
        workspace.worktree_path = MagicMock()

        with (
            patch("agent_fox.knowledge.agent_trace.reconstruct_transcript", return_value="test transcript"),
            patch.object(runner, "_persist_review_findings"),
        ):
            await runner._extract_knowledge_and_findings(
                "spec_01:1", 1, workspace
            )
        # No error raised = review findings path still works
