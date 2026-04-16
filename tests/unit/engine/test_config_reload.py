"""Unit tests for configuration hot-reload at sync barriers.

Test Spec: TS-66-1 through TS-66-11, TS-66-E1 through TS-66-E4
Requirements: 66-REQ-1.*, 66-REQ-2.*, 66-REQ-3.*, 66-REQ-4.*,
              66-REQ-5.*, 66-REQ-6.*, 66-REQ-7.*
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.core.config import (
    AgentFoxConfig,
    ArchetypesConfig,
    OrchestratorConfig,
    PlanningConfig,
)
from agent_fox.engine.barrier import run_sync_barrier_sequence
from agent_fox.engine.engine import Orchestrator
from agent_fox.engine.hot_load import should_trigger_barrier
from agent_fox.engine.state import ExecutionState
from agent_fox.knowledge.audit import AuditEventType

from .conftest import MockSessionRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_hash(content: str) -> str:
    """Compute SHA-256 hex digest of string content."""
    return hashlib.sha256(content.encode()).hexdigest()


def _make_orch(
    tmp_path: Path,
    config: OrchestratorConfig | None = None,
) -> Orchestrator:
    """Create a minimal Orchestrator for testing."""
    from tests.unit.engine.conftest import write_plan_to_db

    db_conn = write_plan_to_db({"spec:1": {}}, [], ["spec:1"])
    runner = MockSessionRunner()
    return Orchestrator(
        config=config or OrchestratorConfig(parallel=1, inter_session_delay=0),
        session_runner_factory=lambda *a, **kw: runner,
        knowledge_db_conn=db_conn,
    )


def _make_state() -> ExecutionState:
    """Create a minimal ExecutionState."""
    return ExecutionState(
        plan_hash="test",
        node_states={"spec:1": "completed"},
        session_history=[],
        total_cost=0.0,
        total_sessions=1,
        started_at="2026-03-31T00:00:00Z",
        updated_at="2026-03-31T00:00:01Z",
    )


# ---------------------------------------------------------------------------
# TS-66-1: Reload triggered at sync barrier
# ---------------------------------------------------------------------------


class TestReloadTriggeredAtBarrier:
    """TS-66-1: _reload_config is called during barrier sequence.

    Requirement: 66-REQ-1.1
    """

    @pytest.mark.asyncio
    async def test_reload_triggered_at_barrier(self, tmp_path: Path) -> None:
        """reload_config_fn is invoked when run_sync_barrier_sequence executes."""
        state = _make_state()
        reload_fn = MagicMock()

        with (
            patch("agent_fox.engine.barrier.verify_worktrees", return_value=[]),
            patch(
                "agent_fox.engine.barrier.sync_develop_bidirectional",
                new_callable=AsyncMock,
            ),
            patch("agent_fox.knowledge.rendering.render_summary"),
        ):
            await run_sync_barrier_sequence(
                state=state,
                sync_interval=5,
                repo_root=tmp_path,
                emit_audit=MagicMock(),
                specs_dir=None,
                hot_load_enabled=False,
                hot_load_fn=AsyncMock(),
                sync_plan_fn=MagicMock(),
                barrier_callback=None,
                knowledge_db_conn=None,
                reload_config_fn=reload_fn,
            )

        reload_fn.assert_called_once()


# ---------------------------------------------------------------------------
# TS-66-2: No-op when hash matches
# ---------------------------------------------------------------------------


class TestNoopWhenHashMatches:
    """TS-66-2: Reload is skipped when file hash hasn't changed.

    Requirements: 66-REQ-1.2, 66-REQ-6.E1
    """

    def test_noop_when_hash_matches(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Config unchanged and no audit event when hash matches."""
        config_content = "[orchestrator]\nmax_cost = 50.0\n"
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)

        orch = _make_orch(tmp_path)
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = _compute_hash(config_content)  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig()  # type: ignore[attr-defined]
        orch._run_id = "test_run"

        original_config = orch._config
        emitted_events: list[dict] = []

        def _capture(*args, **kwargs) -> None:
            emitted_events.append({"args": args, "kwargs": kwargs})

        with patch(
            "agent_fox.engine.engine.emit_audit_event",
            side_effect=_capture,
        ):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        assert orch._config is original_config
        config_reloaded = AuditEventType.CONFIG_RELOADED  # AttributeError — will fail
        assert not any(e["args"][2] == config_reloaded for e in emitted_events)


# ---------------------------------------------------------------------------
# TS-66-3: Reload when hash differs
# ---------------------------------------------------------------------------


class TestReloadWhenHashDiffers:
    """TS-66-3: Config is reloaded when file content changes.

    Requirement: 66-REQ-1.3
    """

    def test_reload_when_hash_differs(self, tmp_path: Path) -> None:
        """Config is re-parsed and applied when hash differs."""
        new_content = "[orchestrator]\nmax_cost = 100.0\n"
        config_file = tmp_path / "config.toml"
        config_file.write_text(new_content)

        orch = _make_orch(tmp_path)
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "old_stale_hash"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig()  # type: ignore[attr-defined]
        orch._run_id = "test_run"

        new_agent_config = AgentFoxConfig(orchestrator=OrchestratorConfig(max_cost=100.0, parallel=1))
        with patch("agent_fox.engine.engine.load_config", return_value=new_agent_config):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        assert orch._config.max_cost == 100.0
        assert orch._config_hash == _compute_hash(new_content)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# TS-66-4: OrchestratorConfig fields updated
# ---------------------------------------------------------------------------


class TestOrchFieldsUpdated:
    """TS-66-4: All mutable OrchestratorConfig fields are updated.

    Requirement: 66-REQ-2.1
    """

    def test_orch_fields_updated(self, tmp_path: Path) -> None:
        """max_cost, max_retries, session_timeout updated after reload."""
        new_content = "[orchestrator]\nmax_cost = 200.0\nmax_retries = 5\n"
        config_file = tmp_path / "config.toml"
        config_file.write_text(new_content)

        orch = _make_orch(tmp_path)
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig()  # type: ignore[attr-defined]
        orch._run_id = "test_run"

        new_orch_cfg = OrchestratorConfig(
            max_cost=200.0,
            max_retries=5,
            session_timeout=60,
            parallel=1,
        )
        new_agent_cfg = AgentFoxConfig(orchestrator=new_orch_cfg)
        with patch(
            "agent_fox.engine.engine.load_config",
            return_value=new_agent_cfg,
        ):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        assert orch._config.max_cost == 200.0
        assert orch._config.max_retries == 5
        assert orch._config.session_timeout == 60


# ---------------------------------------------------------------------------
# TS-66-5: CircuitBreaker reconstructed
# ---------------------------------------------------------------------------


class TestCircuitBreakerRebuilt:
    """TS-66-5: CircuitBreaker is rebuilt with new config.

    Requirement: 66-REQ-2.2
    """

    def test_circuit_breaker_rebuilt(self, tmp_path: Path) -> None:
        """self._circuit is a new instance after reload with changed config."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[orchestrator]\nmax_cost = 999.0\n")

        orch = _make_orch(tmp_path)
        old_circuit = orch._circuit
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig()  # type: ignore[attr-defined]
        orch._run_id = "test_run"

        new_agent_cfg = AgentFoxConfig(orchestrator=OrchestratorConfig(max_cost=999.0, parallel=1))
        with patch(
            "agent_fox.engine.engine.load_config",
            return_value=new_agent_cfg,
        ):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        assert orch._circuit is not old_circuit
        assert orch._circuit._config.max_cost == 999.0


# ---------------------------------------------------------------------------
# TS-66-6: Parallel change logged but not applied
# ---------------------------------------------------------------------------


class TestParallelChangeNotApplied:
    """TS-66-6: parallel change triggers warning and is not applied.

    Requirements: 66-REQ-3.1, 66-REQ-3.2
    """

    def test_parallel_change_warned(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """parallel unchanged and warning logged when new parallel differs."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[orchestrator]\nparallel = 4\n")

        # Start with parallel=2
        start_cfg = OrchestratorConfig(parallel=2, inter_session_delay=0)
        orch = _make_orch(tmp_path, config=start_cfg)
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig(orchestrator=start_cfg)  # type: ignore[attr-defined]
        orch._run_id = "test_run"

        new_agent_cfg = AgentFoxConfig(orchestrator=OrchestratorConfig(parallel=4, inter_session_delay=0))
        with (
            patch(
                "agent_fox.engine.engine.load_config",
                return_value=new_agent_cfg,
            ),
            caplog.at_level(logging.WARNING, logger="agent_fox.engine.engine"),
        ):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        assert orch._config.parallel == 2
        assert orch._is_parallel is True
        assert "parallel" in caplog.text.lower()


# ---------------------------------------------------------------------------
# TS-66-8: ArchetypesConfig updated
# ---------------------------------------------------------------------------


class TestArchetypesConfigUpdated:
    """TS-66-8: Stored ArchetypesConfig is replaced on reload.

    Requirement: 66-REQ-4.2
    """

    def test_archetypes_config_updated(self, tmp_path: Path) -> None:
        """self._archetypes_config references the new ArchetypesConfig after reload."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[archetypes]\nreviewer = false\n")

        orch = _make_orch(tmp_path)
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig()  # type: ignore[attr-defined]
        orch._run_id = "test_run"

        new_arch = ArchetypesConfig(reviewer=False)
        new_agent_cfg = AgentFoxConfig(
            orchestrator=OrchestratorConfig(parallel=1),
            archetypes=new_arch,
        )
        with patch(
            "agent_fox.engine.engine.load_config",
            return_value=new_agent_cfg,
        ):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        assert orch._archetypes_config == new_arch


# ---------------------------------------------------------------------------
# TS-66-9: PlanningConfig updated
# ---------------------------------------------------------------------------


class TestPlanningConfigUpdated:
    """TS-66-9: Stored PlanningConfig is replaced on reload.

    Requirement: 66-REQ-4.3
    """

    def test_planning_config_updated(self, tmp_path: Path) -> None:
        """self._planning_config references the new PlanningConfig after reload."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[planning]\nfile_conflict_detection = true\n")

        orch = _make_orch(tmp_path)
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig()  # type: ignore[attr-defined]
        orch._run_id = "test_run"

        new_plan = PlanningConfig(file_conflict_detection=True)
        new_agent_cfg = AgentFoxConfig(
            orchestrator=OrchestratorConfig(parallel=1),
            planning=new_plan,
        )
        with patch(
            "agent_fox.engine.engine.load_config",
            return_value=new_agent_cfg,
        ):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        assert orch._planning_config == new_plan


# ---------------------------------------------------------------------------
# TS-66-10: Audit event emitted on change
# ---------------------------------------------------------------------------


class TestAuditEventEmitted:
    """TS-66-10: CONFIG_RELOADED event emitted with changed fields.

    Requirements: 66-REQ-6.1, 66-REQ-6.2
    """

    def test_audit_event_emitted(self, tmp_path: Path) -> None:
        """CONFIG_RELOADED audit event emitted with correct changed_fields payload."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[orchestrator]\nmax_cost = 100.0\n")

        start_cfg = OrchestratorConfig(max_cost=50.0, parallel=1, inter_session_delay=0)
        orch = _make_orch(tmp_path, config=start_cfg)
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig(orchestrator=start_cfg)  # type: ignore[attr-defined]
        orch._run_id = "test_run"

        new_agent_cfg = AgentFoxConfig(orchestrator=OrchestratorConfig(max_cost=100.0, parallel=1))
        emitted: list[dict] = []

        def _capture(sink, run_id, event_type, *, payload=None, **kwargs) -> None:
            emitted.append({"event_type": event_type, "payload": payload or {}})

        with (
            patch(
                "agent_fox.engine.engine.load_config",
                return_value=new_agent_cfg,
            ),
            patch(
                "agent_fox.engine.engine.emit_audit_event",
                side_effect=_capture,
            ),
        ):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        # AttributeError until CONFIG_RELOADED is added to AuditEventType:
        config_reloaded_type = AuditEventType.CONFIG_RELOADED
        matching = [e for e in emitted if e["event_type"] == config_reloaded_type]
        assert len(matching) == 1
        changed = matching[0]["payload"]["changed_fields"]
        assert "orchestrator.max_cost" in changed
        assert changed["orchestrator.max_cost"] == {"old": 50.0, "new": 100.0}


# ---------------------------------------------------------------------------
# TS-66-11: Config path stored at construction
# ---------------------------------------------------------------------------


class TestConfigPathStored:
    """TS-66-11: Orchestrator accepts and stores config_path.

    Requirements: 66-REQ-7.1, 66-REQ-7.2
    """

    def test_config_path_stored(self, tmp_path: Path) -> None:
        """Orchestrator stores config_path from constructor parameter."""
        from tests.unit.engine.conftest import write_plan_to_db

        db_conn = write_plan_to_db({"spec:1": {}}, [], ["spec:1"])
        runner = MockSessionRunner()
        config_path = Path(".agent-fox/config.toml")

        orch = Orchestrator(
            config=OrchestratorConfig(parallel=1, inter_session_delay=0),
            session_runner_factory=lambda *a, **kw: runner,
            knowledge_db_conn=db_conn,
            config_path=config_path,
            full_config=AgentFoxConfig(),
        )

        assert orch._config_path == config_path  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# TS-66-E1: Config file missing at reload
# ---------------------------------------------------------------------------


class TestMissingFileKeepsConfig:
    """TS-66-E1: Missing config file keeps current config.

    Requirement: 66-REQ-1.E1
    """

    def test_missing_file_keeps_config(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Config unchanged and warning logged when file doesn't exist."""
        config_file = tmp_path / "nonexistent_config.toml"
        # Do NOT create the file

        orch = _make_orch(tmp_path)
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = ""  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig()  # type: ignore[attr-defined]
        orch._run_id = "test_run"

        original_max_cost = orch._config.max_cost

        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.engine"):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        assert orch._config.max_cost == original_max_cost
        assert caplog.text != ""


# ---------------------------------------------------------------------------
# TS-66-E2: Invalid TOML keeps current config
# ---------------------------------------------------------------------------


class TestInvalidTomlKeepsConfig:
    """TS-66-E2: Parse error preserves current config.

    Requirement: 66-REQ-5.1
    """

    def test_invalid_toml_keeps_config(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Config unchanged and warning logged when load_config raises."""
        from agent_fox.core.errors import ConfigError

        config_file = tmp_path / "config.toml"
        config_file.write_text("not valid toml ][[\n")

        orch = _make_orch(tmp_path)
        original_max_cost = orch._config.max_cost
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig()  # type: ignore[attr-defined]
        orch._run_id = "test_run"

        with (
            patch(
                "agent_fox.engine.engine.load_config",
                side_effect=ConfigError("bad TOML"),
            ),
            caplog.at_level(logging.WARNING, logger="agent_fox.engine.engine"),
        ):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        assert orch._config.max_cost == original_max_cost
        assert caplog.text != ""


# ---------------------------------------------------------------------------
# TS-66-E3: I/O error keeps current config
# ---------------------------------------------------------------------------


class TestIOErrorKeepsConfig:
    """TS-66-E3: I/O error preserves current config.

    Requirement: 66-REQ-5.E1
    """

    def test_io_error_keeps_config(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Config unchanged and warning logged when file read raises OSError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[orchestrator]\n")

        orch = _make_orch(tmp_path)
        original_max_cost = orch._config.max_cost
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig()  # type: ignore[attr-defined]
        orch._run_id = "test_run"

        with (
            patch(
                "pathlib.Path.read_text",
                side_effect=OSError("permission denied"),
            ),
            caplog.at_level(logging.WARNING, logger="agent_fox.engine.engine"),
        ):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        assert orch._config.max_cost == original_max_cost
        assert caplog.text != ""


# ---------------------------------------------------------------------------
# TS-66-E4: sync_interval set to 0 stops future barriers
# ---------------------------------------------------------------------------


class TestSyncIntervalZeroStopsBarriers:
    """TS-66-E4: Disabling sync_interval mid-run stops barriers.

    Requirement: 66-REQ-2.E1
    """

    def test_sync_interval_zero(self, tmp_path: Path) -> None:
        """After reload with sync_interval=0, barrier trigger returns False."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[orchestrator]\nsync_interval = 0\n")

        start_cfg = OrchestratorConfig(sync_interval=5, parallel=1, inter_session_delay=0)
        orch = _make_orch(tmp_path, config=start_cfg)
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig(orchestrator=start_cfg)  # type: ignore[attr-defined]
        orch._run_id = "test_run"

        new_agent_cfg = AgentFoxConfig(orchestrator=OrchestratorConfig(sync_interval=0, parallel=1))
        with patch(
            "agent_fox.engine.engine.load_config",
            return_value=new_agent_cfg,
        ):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        assert orch._config.sync_interval == 0
        # Verify barrier is disabled with sync_interval=0
        assert should_trigger_barrier(5, orch._config.sync_interval) is False
