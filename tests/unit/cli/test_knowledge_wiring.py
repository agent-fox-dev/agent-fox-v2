"""Tests for knowledge pipeline integration in the session runner.

Verifies that knowledge ingestion via KnowledgeProvider and DuckDB sink
recording are wired into the session lifecycle.

Requirements: 114-REQ-3.1, 114-REQ-4.1, 114-REQ-4.E1
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.fox_provider import NoOpKnowledgeProvider
from agent_fox.knowledge.sink import SessionOutcome
from agent_fox.workspace import WorkspaceInfo

_MOCK_KB = MagicMock(spec=KnowledgeDB)


class _TrackingProvider:
    """KnowledgeProvider that records ingest calls."""

    def __init__(self) -> None:
        self.ingest_called = False
        self.ingest_kwargs: dict[str, Any] = {}

    def ingest(self, session_id: str, spec_name: str, context: dict[str, Any]) -> None:
        self.ingest_called = True
        self.ingest_kwargs = {"session_id": session_id, "spec_name": spec_name, "context": context}

    def retrieve(self, spec_name: str, task_description: str) -> list[str]:
        return []


def _make_workspace(tmp_path: Path) -> WorkspaceInfo:
    return WorkspaceInfo(
        path=tmp_path,
        spec_name="test_spec",
        task_group=1,
        branch="feature/test_spec/1",
    )


def _make_outcome(*, status: str = "completed") -> SessionOutcome:
    return SessionOutcome(
        spec_name="test_spec",
        task_group="1",
        node_id="test_spec:1",
        status=status,
        input_tokens=100,
        output_tokens=200,
        duration_ms=5000,
    )


class TestKnowledgeIngestionAfterSession:
    """Verify KnowledgeProvider.ingest() is called after a successful session."""

    @pytest.mark.asyncio
    async def test_ingest_called_on_completed_session(self, tmp_path: Path) -> None:
        """KnowledgeProvider.ingest() is invoked when the session completes."""
        workspace = _make_workspace(tmp_path)
        outcome = _make_outcome(status="completed")

        # Write a session summary artifact
        summary = {"summary": "Implemented feature X.", "tests_added_or_modified": []}
        (tmp_path / ".agent-fox").mkdir(exist_ok=True)
        (tmp_path / ".agent-fox" / "session-summary.json").write_text(json.dumps(summary))

        # Create spec dir under tmp_path so assemble_context doesn't fail
        spec_dir = tmp_path / ".agent-fox" / "specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()
        provider = _TrackingProvider()
        runner = NodeSessionRunner(
            "test_spec:1", config,
            knowledge_db=_MOCK_KB,
            knowledge_provider=provider,
        )

        with (
            patch(
                "agent_fox.engine.session_lifecycle.run_session",
                new_callable=AsyncMock,
                return_value=outcome,
            ),
            patch("agent_fox.engine.session_lifecycle.harvest", new_callable=AsyncMock),
            patch(
                "agent_fox.engine.session_lifecycle.create_worktree",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch(
                "agent_fox.engine.session_lifecycle.destroy_worktree",
                new_callable=AsyncMock,
            ),
        ):
            record = await runner.execute("test_spec:1", 1)

        assert record.status == "completed"
        assert provider.ingest_called
        assert provider.ingest_kwargs["spec_name"] == "test_spec"

    @pytest.mark.asyncio
    async def test_provider_ingest_receives_context(self, tmp_path: Path) -> None:
        """KnowledgeProvider.ingest() receives touched_files, commit_sha, session_status."""
        workspace = _make_workspace(tmp_path)
        outcome = _make_outcome(status="completed")

        summary = {"summary": "Implemented feature X.", "tests_added_or_modified": []}
        (tmp_path / ".agent-fox").mkdir(exist_ok=True)
        (tmp_path / ".agent-fox" / "session-summary.json").write_text(json.dumps(summary))

        spec_dir = tmp_path / ".agent-fox" / "specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()
        provider = _TrackingProvider()
        runner = NodeSessionRunner(
            "test_spec:1", config,
            knowledge_db=_MOCK_KB,
            knowledge_provider=provider,
        )

        with (
            patch(
                "agent_fox.engine.session_lifecycle.run_session",
                new_callable=AsyncMock,
                return_value=outcome,
            ),
            patch("agent_fox.engine.session_lifecycle.harvest", new_callable=AsyncMock),
            patch(
                "agent_fox.engine.session_lifecycle.create_worktree",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch(
                "agent_fox.engine.session_lifecycle.destroy_worktree",
                new_callable=AsyncMock,
            ),
        ):
            await runner.execute("test_spec:1", 1)

        assert provider.ingest_called
        ctx = provider.ingest_kwargs["context"]
        assert "touched_files" in ctx
        assert "commit_sha" in ctx
        assert "session_status" in ctx

    @pytest.mark.asyncio
    async def test_ingest_not_called_on_failed_session(self, tmp_path: Path) -> None:
        """KnowledgeProvider.ingest() is NOT invoked when the session fails."""
        workspace = _make_workspace(tmp_path)
        outcome = _make_outcome(status="failed")

        spec_dir = tmp_path / ".agent-fox" / "specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()
        provider = _TrackingProvider()
        runner = NodeSessionRunner(
            "test_spec:1", config,
            knowledge_db=_MOCK_KB,
            knowledge_provider=provider,
        )

        with (
            patch(
                "agent_fox.engine.session_lifecycle.run_session",
                new_callable=AsyncMock,
                return_value=outcome,
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
        ):
            record = await runner.execute("test_spec:1", 1)

        assert record.status == "failed"
        assert not provider.ingest_called

    @pytest.mark.asyncio
    async def test_ingest_failure_does_not_block_session(self, tmp_path: Path) -> None:
        """KnowledgeProvider.ingest() failure does not block the session."""
        workspace = _make_workspace(tmp_path)
        outcome = _make_outcome(status="completed")

        summary = {"summary": "Implemented feature X."}
        (tmp_path / ".agent-fox").mkdir(exist_ok=True)
        (tmp_path / ".agent-fox" / "session-summary.json").write_text(json.dumps(summary))

        spec_dir = tmp_path / ".agent-fox" / "specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()

        class _FailingProvider:
            def ingest(self, session_id: str, spec_name: str, context: dict[str, Any]) -> None:
                raise RuntimeError("API error")

            def retrieve(self, spec_name: str, task_description: str) -> list[str]:
                return []

        runner = NodeSessionRunner(
            "test_spec:1", config,
            knowledge_db=_MOCK_KB,
            knowledge_provider=_FailingProvider(),
        )

        with (
            patch(
                "agent_fox.engine.session_lifecycle.run_session",
                new_callable=AsyncMock,
                return_value=outcome,
            ),
            patch("agent_fox.engine.session_lifecycle.harvest", new_callable=AsyncMock),
            patch(
                "agent_fox.engine.session_lifecycle.create_worktree",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch(
                "agent_fox.engine.session_lifecycle.destroy_worktree",
                new_callable=AsyncMock,
            ),
        ):
            record = await runner.execute("test_spec:1", 1)

        # Session is still completed despite ingestion failure
        assert record.status == "completed"
