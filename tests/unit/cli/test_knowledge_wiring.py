"""Tests for knowledge pipeline integration in the session runner.

Verifies that fact extraction, knowledge injection, and DuckDB sink
recording are wired into the session lifecycle.

Requirements: 05-REQ-1.1, 05-REQ-4.1, 11-REQ-4.2, 12-REQ-1.1
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.sink import SessionOutcome
from agent_fox.workspace import WorkspaceInfo

_MOCK_KB = MagicMock(spec=KnowledgeDB)


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


class TestFactExtractionAfterSession:
    """Verify extract_facts is called after a successful session."""

    @pytest.mark.asyncio
    async def test_extract_called_on_completed_session(self, tmp_path: Path) -> None:
        """extract_facts is invoked when the session completes successfully."""
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
        runner = NodeSessionRunner("test_spec:1", config, knowledge_db=_MOCK_KB)

        mock_extract = AsyncMock()

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
            patch(
                "agent_fox.engine.session_lifecycle.extract_and_store_knowledge",
                mock_extract,
            ),
        ):
            record = await runner.execute("test_spec:1", 1)

        assert record.status == "completed"
        mock_extract.assert_called_once()
        call_args = mock_extract.call_args
        assert call_args.kwargs["spec_name"] == "test_spec"

    @pytest.mark.asyncio
    async def test_embedder_passed_to_extract(self, tmp_path: Path) -> None:
        """Regression: embedder must be forwarded to extract_and_store_knowledge (fixes #453)."""
        workspace = _make_workspace(tmp_path)
        outcome = _make_outcome(status="completed")

        summary = {"summary": "Implemented feature X.", "tests_added_or_modified": []}
        (tmp_path / ".agent-fox").mkdir(exist_ok=True)
        (tmp_path / ".agent-fox" / "session-summary.json").write_text(json.dumps(summary))

        spec_dir = tmp_path / ".agent-fox" / "specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()
        mock_embedder = MagicMock()
        runner = NodeSessionRunner("test_spec:1", config, knowledge_db=_MOCK_KB, embedder=mock_embedder)

        mock_extract = AsyncMock()

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
            patch(
                "agent_fox.engine.session_lifecycle.extract_and_store_knowledge",
                mock_extract,
            ),
        ):
            await runner.execute("test_spec:1", 1)

        mock_extract.assert_called_once()
        assert mock_extract.call_args.kwargs["embedder"] is mock_embedder

    @pytest.mark.asyncio
    async def test_extract_not_called_on_failed_session(self, tmp_path: Path) -> None:
        """extract_and_store_knowledge is NOT invoked when the session fails."""
        workspace = _make_workspace(tmp_path)
        outcome = _make_outcome(status="failed")

        spec_dir = tmp_path / ".agent-fox" / "specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()
        runner = NodeSessionRunner("test_spec:1", config, knowledge_db=_MOCK_KB)

        mock_extract = AsyncMock()

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
            patch(
                "agent_fox.engine.session_lifecycle.extract_and_store_knowledge",
                mock_extract,
            ),
        ):
            record = await runner.execute("test_spec:1", 1)

        assert record.status == "failed"
        mock_extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_failure_does_not_block_session(self, tmp_path: Path) -> None:
        """Extract failure does not block the session."""
        workspace = _make_workspace(tmp_path)
        outcome = _make_outcome(status="completed")

        summary = {"summary": "Implemented feature X."}
        (tmp_path / ".agent-fox").mkdir(exist_ok=True)
        (tmp_path / ".agent-fox" / "session-summary.json").write_text(json.dumps(summary))

        spec_dir = tmp_path / ".agent-fox" / "specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()
        runner = NodeSessionRunner("test_spec:1", config, knowledge_db=_MOCK_KB)

        mock_extract = AsyncMock(side_effect=RuntimeError("API error"))

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
            patch(
                "agent_fox.engine.session_lifecycle.extract_and_store_knowledge",
                mock_extract,
            ),
        ):
            record = await runner.execute("test_spec:1", 1)

        # Session is still completed despite extraction failure
        assert record.status == "completed"
