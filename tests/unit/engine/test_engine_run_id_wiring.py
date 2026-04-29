"""Unit test for engine wiring: set_run_id called on knowledge provider.

Verifies that when the engine initializes a run via _init_run(), it calls
set_run_id() on the knowledge provider with the generated run ID.

Test Spec: TS-120-4
Requirements: 120-REQ-1.3
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from agent_fox.core.config import KnowledgeProviderConfig, OrchestratorConfig
from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider


class TestEngineCallsSetRunId:
    """Verify the engine wires run_id to the knowledge provider."""

    def test_init_run_calls_set_run_id(self, tmp_path: Path) -> None:
        """After _init_run(), the knowledge provider's set_run_id has been called
        with the generated run ID.

        The test constructs a minimal Orchestrator with a real
        FoxKnowledgeProvider (mocked DB) and verifies set_run_id is called.
        """
        import duckdb

        from agent_fox.engine.engine import Orchestrator
        from agent_fox.knowledge.db import KnowledgeDB
        from agent_fox.knowledge.migrations import run_migrations

        conn = duckdb.connect(":memory:")
        run_migrations(conn)

        db = KnowledgeDB.__new__(KnowledgeDB)
        db._conn = conn

        provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())

        # Write a minimal plan.json so _load_graph succeeds
        plan_dir = tmp_path / ".agent-fox"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan = {
            "metadata": {
                "created_at": "2026-01-01T00:00:00",
                "fast_mode": False,
                "filtered_spec": None,
                "version": "0.1.0",
            },
            "nodes": {
                "spec_a:1": {
                    "id": "spec_a:1",
                    "spec_name": "spec_a",
                    "group_number": 1,
                    "title": "Task 1",
                    "optional": False,
                    "status": "pending",
                    "subtask_count": 0,
                    "body": "",
                    "archetype": "coder",
                },
            },
            "edges": [],
            "order": ["spec_a:1"],
        }
        (plan_dir / "plan.json").write_text(json.dumps(plan))

        mock_runner_factory = MagicMock()

        # The Orchestrator needs a knowledge_provider parameter (120-REQ-1.3).
        # This test will fail until the engine is updated to accept and use it.
        try:
            orchestrator = Orchestrator(
                OrchestratorConfig(parallel=1, inter_session_delay=0),
                mock_runner_factory,
                agent_dir=plan_dir,
                knowledge_db_conn=conn,
                knowledge_provider=provider,
            )
        except TypeError:
            # Expected: Orchestrator doesn't accept knowledge_provider yet
            # When the implementation is added, this will succeed and
            # the assertion below will be reached.
            raise AssertionError(
                "Orchestrator does not accept 'knowledge_provider' parameter yet. "
                "120-REQ-1.3 requires the engine to call set_run_id() on the provider."
            )

        orchestrator._init_run()

        # Verify set_run_id was called with the generated run ID
        assert provider._run_id is not None, "set_run_id() was not called"
        assert provider._run_id != "", "set_run_id() was called with empty string"
        assert provider._run_id == orchestrator._run_id, (
            f"Provider run_id ({provider._run_id}) != engine run_id ({orchestrator._run_id})"
        )

        conn.close()
