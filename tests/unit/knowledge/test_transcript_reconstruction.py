"""Tests for full transcript reconstruction from agent trace JSONL.

Suite 1: Full Transcript Reconstruction (TS-1.1 through TS-1.5)

Requirements: 113-REQ-1.1, 113-REQ-1.2, 113-REQ-1.3,
              113-REQ-1.E1, 113-REQ-1.E2
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the new function — will fail with ImportError until implemented (task 2.1).
from agent_fox.knowledge.agent_trace import reconstruct_transcript


class TestReconstructTranscript:
    """TS-1.1, TS-1.2, TS-1.3: reconstruct_transcript unit tests."""

    def test_reconstruct_includes_all_target_messages(self, tmp_path: Path) -> None:
        """TS-1.1: Reconstructed transcript contains all assistant.message content
        for the target node_id, in JSONL order.
        """
        jsonl_path = tmp_path / "agent_test-run.jsonl"
        events = [
            {"event_type": "assistant.message", "run_id": "test-run", "node_id": "spec:1", "content": "Message A"},
            {"event_type": "assistant.message", "run_id": "test-run", "node_id": "other:1", "content": "Noise 1"},
            {"event_type": "assistant.message", "run_id": "test-run", "node_id": "spec:1", "content": "Message B"},
            {"event_type": "tool.use", "run_id": "test-run", "node_id": "spec:1", "tool_name": "Read"},
            {"event_type": "assistant.message", "run_id": "test-run", "node_id": "other:1", "content": "Noise 2"},
            {"event_type": "assistant.message", "run_id": "test-run", "node_id": "spec:1", "content": "Message C"},
        ]
        jsonl_path.write_text("\n".join(json.dumps(e) for e in events))

        result = reconstruct_transcript(tmp_path, "test-run", "spec:1")

        # All three messages appear
        assert "Message A" in result
        assert "Message B" in result
        assert "Message C" in result

    def test_reconstruct_excludes_other_node_content(self, tmp_path: Path) -> None:
        """TS-1.1: Noise from other:1 does not appear in spec:1 transcript."""
        jsonl_path = tmp_path / "agent_test-run.jsonl"
        events = [
            {"event_type": "assistant.message", "run_id": "test-run", "node_id": "spec:1", "content": "Message A"},
            {"event_type": "assistant.message", "run_id": "test-run", "node_id": "other:1", "content": "Noise 1"},
        ]
        jsonl_path.write_text("\n".join(json.dumps(e) for e in events))

        result = reconstruct_transcript(tmp_path, "test-run", "spec:1")

        assert "Noise 1" not in result

    def test_reconstruct_preserves_message_order(self, tmp_path: Path) -> None:
        """TS-1.1: Messages appear in JSONL file order (A before B before C)."""
        jsonl_path = tmp_path / "agent_test-run.jsonl"
        events = [
            {"event_type": "assistant.message", "run_id": "test-run", "node_id": "spec:1", "content": "Message A"},
            {"event_type": "assistant.message", "run_id": "test-run", "node_id": "spec:1", "content": "Message B"},
            {"event_type": "assistant.message", "run_id": "test-run", "node_id": "spec:1", "content": "Message C"},
        ]
        jsonl_path.write_text("\n".join(json.dumps(e) for e in events))

        result = reconstruct_transcript(tmp_path, "test-run", "spec:1")

        pos_a = result.index("Message A")
        pos_b = result.index("Message B")
        pos_c = result.index("Message C")
        assert pos_a < pos_b < pos_c

    def test_fallback_when_jsonl_missing(self, tmp_path: Path) -> None:
        """TS-1.2: Returns empty string when JSONL file does not exist.
        No exception raised.

        Requirements: 113-REQ-1.E1
        """
        result = reconstruct_transcript(tmp_path, "missing-run", "spec:1")
        assert result == ""

    def test_skip_when_zero_assistant_messages(self, tmp_path: Path) -> None:
        """TS-1.3: Returns empty string when JSONL contains only tool.use events
        for the target node_id.

        Requirements: 113-REQ-1.E2
        """
        jsonl_path = tmp_path / "agent_test-run.jsonl"
        events = [
            {"event_type": "tool.use", "run_id": "test-run", "node_id": "spec:1", "tool_name": "Read"},
            {"event_type": "tool.use", "run_id": "test-run", "node_id": "spec:1", "tool_name": "Bash"},
        ]
        jsonl_path.write_text("\n".join(json.dumps(e) for e in events))

        result = reconstruct_transcript(tmp_path, "test-run", "spec:1")

        assert result == ""


class TestLifecycleUsesReconstructedTranscript:
    """TS-1.4: Integration — lifecycle uses reconstructed transcript.

    Requirements: 113-REQ-1.1, 113-REQ-1.2, 113-REQ-1.3
    """

    @pytest.mark.asyncio
    async def test_extract_uses_full_transcript_not_summary(
        self,
        tmp_path: Path,
    ) -> None:
        """TS-1.4: _extract_knowledge_and_findings calls extract_and_store_knowledge
        with the full reconstructed transcript, not the session summary.
        """

        # Build a JSONL trace with substantial content
        long_content = "A" * 500  # Each message contributes 500 chars
        events = [
            {
                "event_type": "assistant.message",
                "run_id": "test-run",
                "node_id": "05_foo:1",
                "content": f"Message {i}: {long_content}",
            }
            for i in range(5)
        ]
        audit_dir = tmp_path / ".agent-fox" / "audit"
        audit_dir.mkdir(parents=True)
        jsonl_path = audit_dir / "agent_test-run.jsonl"
        jsonl_path.write_text("\n".join(json.dumps(e) for e in events))

        # Create a session-summary.json with short summary
        summary_dir = tmp_path / ".agent-fox"
        summary_dir.mkdir(parents=True, exist_ok=True)
        (summary_dir / "session-summary.json").write_text('{"summary": "Short summary only."}')

        captured_transcript: list[str] = []

        async def fake_extract(transcript: str, *args, **kwargs) -> None:
            captured_transcript.append(transcript)

        with patch(
            "agent_fox.engine.session_lifecycle.extract_and_store_knowledge",
            side_effect=fake_extract,
        ):
            # NodeSessionRunner setup is complex — test the transcript
            # selection logic directly via _extract_knowledge_and_findings.
            # This test asserts that the reconstructed transcript (> 2000 chars)
            # is passed as the transcript, not the short summary.
            runner = _make_minimal_runner(tmp_path, "05_foo:1")
            await runner._extract_knowledge_and_findings(
                node_id="05_foo:1",
                attempt=1,
                workspace=MagicMock(),
            )

        assert len(captured_transcript) == 1
        transcript_used = captured_transcript[0]
        # The full transcript should contain the long content, not just the summary
        assert "Short summary only." not in transcript_used
        assert "Message 0" in transcript_used or len(transcript_used) > 2000

    @pytest.mark.asyncio
    async def test_fallback_when_trace_empty(
        self,
        tmp_path: Path,
    ) -> None:
        """TS-1.5: Falls back to _build_fallback_input when trace file is absent.
        Warning is logged.

        Requirements: 113-REQ-1.E1, 113-REQ-1.3
        """

        captured_transcript: list[str] = []

        async def fake_extract(transcript: str, *args, **kwargs) -> None:
            captured_transcript.append(transcript)

        fallback_text = "F" * 3000  # > 2000 chars

        with (
            patch(
                "agent_fox.engine.session_lifecycle.extract_and_store_knowledge",
                side_effect=fake_extract,
            ),
            patch(
                "agent_fox.engine.session_lifecycle.NodeSessionRunner._build_fallback_input",
                return_value=fallback_text,
            ),
        ):
            runner = _make_minimal_runner(tmp_path, "05_foo:1")
            await runner._extract_knowledge_and_findings(
                node_id="05_foo:1",
                attempt=1,
                workspace=MagicMock(),
            )

        # Fallback content should have been passed to extract_and_store_knowledge
        assert len(captured_transcript) == 1
        assert captured_transcript[0] == fallback_text


# ---------------------------------------------------------------------------
# Helper: build a minimal NodeSessionRunner for testing lifecycle methods
# ---------------------------------------------------------------------------


def _make_minimal_runner(tmp_path: Path, node_id: str):
    """Create a NodeSessionRunner with minimal config for testing."""
    import duckdb

    from agent_fox.core.config import AgentFoxConfig
    from agent_fox.engine.session_lifecycle import NodeSessionRunner
    from agent_fox.knowledge.db import KnowledgeDB
    from agent_fox.knowledge.migrations import run_migrations

    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = conn

    config = AgentFoxConfig()

    runner = NodeSessionRunner.__new__(NodeSessionRunner)
    runner._node_id = node_id
    runner._spec_name = node_id.split(":")[0] if ":" in node_id else node_id
    runner._task_group = int(node_id.split(":")[1]) if ":" in node_id else 1
    runner._run_id = "test-run"
    runner._audit_dir = tmp_path / ".agent-fox" / "audit"
    runner._audit_dir.mkdir(parents=True, exist_ok=True)
    runner._agent_fox_dir = tmp_path / ".agent-fox"
    runner._config = config
    runner._knowledge_db = db
    runner._sink = None
    runner._embedder = None
    runner._archetype = "coder"
    runner._mode = None
    runner._trace_enabled = True
    return runner
