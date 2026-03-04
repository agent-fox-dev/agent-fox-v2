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

from agent_fox.cli.code import _NodeSessionRunner
from agent_fox.core.config import AgentFoxConfig
from agent_fox.memory.types import Fact
from agent_fox.knowledge.sink import SessionOutcome
from agent_fox.workspace.worktree import WorkspaceInfo


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


def _make_fact(content: str = "Test fact") -> Fact:
    return Fact(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        content=content,
        category="gotcha",
        spec_name="test_spec",
        keywords=["test"],
        confidence="high",
        created_at="2026-03-03T00:00:00+00:00",
        supersedes=None,
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
        (tmp_path / ".session-summary.json").write_text(json.dumps(summary))

        # Create spec dir so assemble_context doesn't fail
        spec_dir = Path.cwd() / ".specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()
        runner = _NodeSessionRunner("test_spec:1", config)

        mock_extract = AsyncMock(return_value=[_make_fact()])

        with (
            patch(
                "agent_fox.cli.code.run_session",
                new_callable=AsyncMock,
                return_value=outcome,
            ),
            patch("agent_fox.cli.code.harvest", new_callable=AsyncMock),
            patch(
                "agent_fox.cli.code.create_worktree",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch("agent_fox.cli.code.destroy_worktree", new_callable=AsyncMock),
            patch("agent_fox.cli.code.extract_facts", mock_extract),
            patch("agent_fox.cli.code.append_facts"),
        ):
            record = await runner.execute("test_spec:1", 1)

        assert record.status == "completed"
        mock_extract.assert_called_once()
        call_args = mock_extract.call_args
        assert "test_spec" in call_args.args or "test_spec" in str(call_args)

    @pytest.mark.asyncio
    async def test_extract_not_called_on_failed_session(self, tmp_path: Path) -> None:
        """extract_facts is NOT invoked when the session fails."""
        workspace = _make_workspace(tmp_path)
        outcome = _make_outcome(status="failed")

        spec_dir = Path.cwd() / ".specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()
        runner = _NodeSessionRunner("test_spec:1", config)

        mock_extract = AsyncMock(return_value=[])

        with (
            patch(
                "agent_fox.cli.code.run_session",
                new_callable=AsyncMock,
                return_value=outcome,
            ),
            patch(
                "agent_fox.cli.code.create_worktree",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch("agent_fox.cli.code.destroy_worktree", new_callable=AsyncMock),
            patch("agent_fox.cli.code.extract_facts", mock_extract),
        ):
            record = await runner.execute("test_spec:1", 1)

        assert record.status == "failed"
        mock_extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_failure_does_not_block_session(self, tmp_path: Path) -> None:
        """If extract_facts raises, the session still returns successfully."""
        workspace = _make_workspace(tmp_path)
        outcome = _make_outcome(status="completed")

        summary = {"summary": "Implemented feature X."}
        (tmp_path / ".session-summary.json").write_text(json.dumps(summary))

        spec_dir = Path.cwd() / ".specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()
        runner = _NodeSessionRunner("test_spec:1", config)

        mock_extract = AsyncMock(side_effect=RuntimeError("API error"))

        with (
            patch(
                "agent_fox.cli.code.run_session",
                new_callable=AsyncMock,
                return_value=outcome,
            ),
            patch("agent_fox.cli.code.harvest", new_callable=AsyncMock),
            patch(
                "agent_fox.cli.code.create_worktree",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch("agent_fox.cli.code.destroy_worktree", new_callable=AsyncMock),
            patch("agent_fox.cli.code.extract_facts", mock_extract),
        ):
            record = await runner.execute("test_spec:1", 1)

        # Session is still completed despite extraction failure
        assert record.status == "completed"


class TestKnowledgeInjectionIntoContext:
    """Verify that memory facts are loaded and passed to assemble_context."""

    @pytest.mark.asyncio
    async def test_memory_facts_passed_to_context(self, tmp_path: Path) -> None:
        """assemble_context receives memory_facts when facts exist."""
        workspace = _make_workspace(tmp_path)
        outcome = _make_outcome(status="completed")

        spec_dir = Path.cwd() / ".specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()
        runner = _NodeSessionRunner("test_spec:1", config)

        facts = [_make_fact("Pydantic requires ConfigDict")]
        mock_assemble = MagicMock(return_value="context text")

        with (
            patch(
                "agent_fox.cli.code.run_session",
                new_callable=AsyncMock,
                return_value=outcome,
            ),
            patch("agent_fox.cli.code.harvest", new_callable=AsyncMock),
            patch(
                "agent_fox.cli.code.create_worktree",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch("agent_fox.cli.code.destroy_worktree", new_callable=AsyncMock),
            patch("agent_fox.cli.code.assemble_context", mock_assemble),
            patch("agent_fox.cli.code.load_all_facts", return_value=facts),
            patch("agent_fox.cli.code.select_relevant_facts", return_value=facts),
            patch(
                "agent_fox.cli.code.extract_facts",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await runner.execute("test_spec:1", 1)

        mock_assemble.assert_called_once()
        _, kwargs = mock_assemble.call_args
        # memory_facts should be a list of fact content strings
        assert "memory_facts" in kwargs
        assert len(kwargs["memory_facts"]) == 1
        assert "Pydantic requires ConfigDict" in kwargs["memory_facts"][0]

    @pytest.mark.asyncio
    async def test_empty_facts_passes_none(self, tmp_path: Path) -> None:
        """When no facts match, memory_facts is None."""
        workspace = _make_workspace(tmp_path)
        outcome = _make_outcome(status="completed")

        spec_dir = Path.cwd() / ".specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()
        runner = _NodeSessionRunner("test_spec:1", config)

        mock_assemble = MagicMock(return_value="context text")

        with (
            patch(
                "agent_fox.cli.code.run_session",
                new_callable=AsyncMock,
                return_value=outcome,
            ),
            patch("agent_fox.cli.code.harvest", new_callable=AsyncMock),
            patch(
                "agent_fox.cli.code.create_worktree",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch("agent_fox.cli.code.destroy_worktree", new_callable=AsyncMock),
            patch("agent_fox.cli.code.assemble_context", mock_assemble),
            patch("agent_fox.cli.code.load_all_facts", return_value=[]),
            patch("agent_fox.cli.code.select_relevant_facts", return_value=[]),
            patch(
                "agent_fox.cli.code.extract_facts",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await runner.execute("test_spec:1", 1)

        mock_assemble.assert_called_once()
        _, kwargs = mock_assemble.call_args
        assert kwargs.get("memory_facts") is None


class TestSinkWiring:
    """Verify DuckDB sink is created and records session outcomes."""

    @pytest.mark.asyncio
    async def test_sink_records_outcome_on_completion(self, tmp_path: Path) -> None:
        """SinkDispatcher.record_session_outcome is called after session."""
        workspace = _make_workspace(tmp_path)
        outcome = _make_outcome(status="completed")

        spec_dir = Path.cwd() / ".specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()
        mock_sink = MagicMock()
        runner = _NodeSessionRunner(
            "test_spec:1",
            config,
            sink_dispatcher=mock_sink,
        )

        with (
            patch(
                "agent_fox.cli.code.run_session",
                new_callable=AsyncMock,
                return_value=outcome,
            ),
            patch("agent_fox.cli.code.harvest", new_callable=AsyncMock),
            patch(
                "agent_fox.cli.code.create_worktree",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch("agent_fox.cli.code.destroy_worktree", new_callable=AsyncMock),
            patch(
                "agent_fox.cli.code.extract_facts",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("agent_fox.cli.code.load_all_facts", return_value=[]),
            patch("agent_fox.cli.code.select_relevant_facts", return_value=[]),
        ):
            await runner.execute("test_spec:1", 1)

        mock_sink.record_session_outcome.assert_called_once()

    @pytest.mark.asyncio
    async def test_sink_failure_does_not_block_session(self, tmp_path: Path) -> None:
        """If the sink raises, the session still returns successfully."""
        workspace = _make_workspace(tmp_path)
        outcome = _make_outcome(status="completed")

        spec_dir = Path.cwd() / ".specs" / "test_spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        config = AgentFoxConfig()
        mock_sink = MagicMock()
        mock_sink.record_session_outcome.side_effect = RuntimeError("DB error")
        runner = _NodeSessionRunner(
            "test_spec:1",
            config,
            sink_dispatcher=mock_sink,
        )

        with (
            patch(
                "agent_fox.cli.code.run_session",
                new_callable=AsyncMock,
                return_value=outcome,
            ),
            patch("agent_fox.cli.code.harvest", new_callable=AsyncMock),
            patch(
                "agent_fox.cli.code.create_worktree",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch("agent_fox.cli.code.destroy_worktree", new_callable=AsyncMock),
            patch(
                "agent_fox.cli.code.extract_facts",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("agent_fox.cli.code.load_all_facts", return_value=[]),
            patch("agent_fox.cli.code.select_relevant_facts", return_value=[]),
        ):
            record = await runner.execute("test_spec:1", 1)

        assert record.status == "completed"
