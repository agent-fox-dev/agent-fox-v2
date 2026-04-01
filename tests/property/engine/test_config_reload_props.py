"""Property tests for configuration hot-reload at sync barriers.

Test Spec: TS-66-P1 through TS-66-P6
Properties: Property 1-6 from design.md
Requirements: 66-REQ-1.2, 66-REQ-2.1, 66-REQ-2.2, 66-REQ-3.1, 66-REQ-3.2,
              66-REQ-5.1, 66-REQ-5.E1, 66-REQ-1.E1, 66-REQ-6.1, 66-REQ-6.2,
              66-REQ-6.E1
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.core.config import (
    AgentFoxConfig,
    OrchestratorConfig,
)
from agent_fox.engine.engine import Orchestrator
from agent_fox.knowledge.audit import AuditEventType
from tests.unit.engine.conftest import MockSessionRunner, make_plan_json

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
    """Create a minimal Orchestrator for property testing."""
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(make_plan_json({"spec:1": {}}, [], ["spec:1"]))
    state_path = tmp_path / "state.jsonl"
    runner = MockSessionRunner()
    return Orchestrator(
        config=config or OrchestratorConfig(parallel=1, inter_session_delay=0),
        plan_path=plan_path,
        state_path=state_path,
        session_runner_factory=lambda *a, **kw: runner,
    )


# Hypothesis strategies


@st.composite
def orch_config_strategy(draw: st.DrawFn) -> OrchestratorConfig:
    """Strategy for generating arbitrary OrchestratorConfig instances."""
    return OrchestratorConfig(
        max_cost=draw(
            st.one_of(st.none(), st.floats(min_value=0.1, max_value=10000.0))
        ),
        max_retries=draw(st.integers(min_value=0, max_value=10)),
        session_timeout=draw(st.integers(min_value=1, max_value=120)),
        sync_interval=draw(st.integers(min_value=0, max_value=20)),
        parallel=1,  # keep parallel fixed so immutability guard doesn't interfere
        inter_session_delay=0,
    )


@st.composite
def config_pair_strategy(draw: st.DrawFn) -> tuple[AgentFoxConfig, AgentFoxConfig]:
    """Strategy generating (old, new) AgentFoxConfig pairs that differ."""
    old_cost = draw(st.floats(min_value=0.1, max_value=100.0, allow_nan=False))
    new_cost = draw(st.floats(min_value=100.1, max_value=200.0, allow_nan=False))
    old_cfg = AgentFoxConfig(
        orchestrator=OrchestratorConfig(max_cost=old_cost, parallel=1)
    )
    new_cfg = AgentFoxConfig(
        orchestrator=OrchestratorConfig(max_cost=new_cost, parallel=1)
    )
    return old_cfg, new_cfg


# ---------------------------------------------------------------------------
# TS-66-P1: No-op on unchanged config
# ---------------------------------------------------------------------------


class TestNoopUnchangedProperty:
    """TS-66-P1: Unchanged file produces zero state changes and no audit event.

    Property 1 from design.md.
    Requirements: 66-REQ-1.2, 66-REQ-6.E1
    """

    @given(
        max_cost=st.floats(min_value=0.1, max_value=10000.0, allow_nan=False),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_noop_unchanged(self, max_cost: float, tmp_path: Path) -> None:
        """If hash matches file content, _reload_config is a complete no-op."""
        config_content = f"[orchestrator]\nmax_cost = {max_cost}\n"
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        current_hash = _compute_hash(config_content)

        orch = _make_orch(tmp_path)
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = current_hash  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig()  # type: ignore[attr-defined]
        orch._run_id = "prop_test"

        original_config = orch._config
        original_circuit = orch._circuit
        emitted: list[Any] = []

        def _capture(*args, **kwargs) -> None:
            emitted.append(args)

        with patch("agent_fox.engine.config_reload.emit_audit_event", side_effect=_capture):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        assert orch._config is original_config
        assert orch._circuit is original_circuit
        config_reloaded = AuditEventType.CONFIG_RELOADED  # AttributeError — will fail
        assert not any(a[2] == config_reloaded for a in emitted)


# ---------------------------------------------------------------------------
# TS-66-P2: All mutable fields updated
# ---------------------------------------------------------------------------


class TestMutableFieldsUpdatedProperty:
    """TS-66-P2: Every mutable OrchestratorConfig field is updated on reload.

    Property 2 from design.md.
    Requirement: 66-REQ-2.1
    """

    _MUTABLE_FIELDS = [
        "max_cost",
        "max_retries",
        "session_timeout",
        "inter_session_delay",
        "sync_interval",
        "hot_load",
        "max_sessions",
        "max_blocked_fraction",
        "quality_gate",
        "quality_gate_timeout",
        "max_budget_usd",
        "causal_context_limit",
        "audit_retention_runs",
    ]

    @given(new_cfg=orch_config_strategy())
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_mutable_fields_updated(
        self, new_cfg: OrchestratorConfig, tmp_path: Path
    ) -> None:
        """After reload, all mutable OrchestratorConfig fields match new config."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[orchestrator]\n")  # Content differs from hash

        orch = _make_orch(tmp_path)
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale_hash"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig()  # type: ignore[attr-defined]
        orch._run_id = "prop_test"

        new_agent_cfg = AgentFoxConfig(orchestrator=new_cfg)
        with patch("agent_fox.engine.config_reload.load_config", return_value=new_agent_cfg):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        for field_name in self._MUTABLE_FIELDS:
            expected = getattr(new_cfg, field_name)
            actual = getattr(orch._config, field_name)
            assert actual == expected, (
                f"Field {field_name}: expected {expected!r}, got {actual!r}"
            )


# ---------------------------------------------------------------------------
# TS-66-P3: CircuitBreaker reconstructed
# ---------------------------------------------------------------------------


class TestCircuitBreakerRebuiltProperty:
    """TS-66-P3: CircuitBreaker always uses latest config after reload.

    Property 3 from design.md.
    Requirement: 66-REQ-2.2
    """

    @given(
        max_cost=st.floats(min_value=0.1, max_value=10000.0, allow_nan=False),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_circuit_breaker_rebuilt(self, max_cost: float, tmp_path: Path) -> None:
        """CircuitBreaker._config.max_cost matches new config after reload."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(f"[orchestrator]\nmax_cost = {max_cost}\n")

        orch = _make_orch(tmp_path)
        old_circuit = orch._circuit
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig()  # type: ignore[attr-defined]
        orch._run_id = "prop_test"

        new_agent_cfg = AgentFoxConfig(
            orchestrator=OrchestratorConfig(max_cost=max_cost, parallel=1)
        )
        with patch("agent_fox.engine.config_reload.load_config", return_value=new_agent_cfg):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        assert orch._circuit is not old_circuit
        assert orch._circuit._config.max_cost == max_cost


# ---------------------------------------------------------------------------
# TS-66-P4: Parallel is immutable
# ---------------------------------------------------------------------------


class TestParallelImmutableProperty:
    """TS-66-P4: parallel value never changes after reload.

    Property 4 from design.md.
    Requirements: 66-REQ-3.1, 66-REQ-3.2
    """

    @given(
        new_parallel=st.integers(min_value=2, max_value=8),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_parallel_immutable(self, new_parallel: int, tmp_path: Path) -> None:
        """self._config.parallel remains 1 regardless of new config parallel value."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(f"[orchestrator]\nparallel = {new_parallel}\n")

        # Start with parallel=1
        start_cfg = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orch = _make_orch(tmp_path, config=start_cfg)
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig(orchestrator=start_cfg)  # type: ignore[attr-defined]
        orch._run_id = "prop_test"

        new_orch_cfg = OrchestratorConfig(parallel=new_parallel, inter_session_delay=0)
        new_agent_cfg = AgentFoxConfig(orchestrator=new_orch_cfg)
        with patch("agent_fox.engine.config_reload.load_config", return_value=new_agent_cfg):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        # parallel must not have changed
        assert orch._config.parallel == 1


# ---------------------------------------------------------------------------
# TS-66-P5: Parse errors preserve config
# ---------------------------------------------------------------------------


class TestErrorsPreserveConfigProperty:
    """TS-66-P5: Any error during reload leaves state unchanged.

    Property 5 from design.md.
    Requirements: 66-REQ-5.1, 66-REQ-5.E1, 66-REQ-1.E1
    """

    @given(
        exc_class=st.sampled_from([OSError, FileNotFoundError, ValueError]),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_errors_preserve_config(
        self,
        exc_class: type[Exception],
        tmp_path: Path,
    ) -> None:
        """Config and CircuitBreaker unchanged when load_config raises."""
        from agent_fox.core.errors import ConfigError

        config_file = tmp_path / "config.toml"
        config_file.write_text("[orchestrator]\n")

        orch = _make_orch(tmp_path)
        old_config = orch._config
        old_circuit = orch._circuit
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale"  # type: ignore[attr-defined]
        orch._full_config = AgentFoxConfig()  # type: ignore[attr-defined]
        orch._run_id = "prop_test"

        error_types = [exc_class, ConfigError]
        for err_type in error_types:
            with patch(
                "agent_fox.engine.config_reload.load_config",
                side_effect=err_type("test error"),
            ):
                orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

            assert orch._config is old_config
            assert orch._circuit is old_circuit


# ---------------------------------------------------------------------------
# TS-66-P6: Audit event captures exact diff
# ---------------------------------------------------------------------------


class TestAuditExactDiffProperty:
    """TS-66-P6: Audit event payload contains exactly the changed fields.

    Property 6 from design.md.
    Requirements: 66-REQ-6.1, 66-REQ-6.2
    """

    @given(cfgs=config_pair_strategy())
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_audit_exact_diff(
        self,
        cfgs: tuple[AgentFoxConfig, AgentFoxConfig],
        tmp_path: Path,
    ) -> None:
        """Audit event changed_fields matches diff between old and new config."""
        old_cfg, new_cfg = cfgs

        # Import diff_configs — will fail with ImportError until implemented
        from agent_fox.engine.engine import diff_configs  # noqa: PLC0415

        config_file = tmp_path / "config.toml"
        config_file.write_text("[orchestrator]\n")

        orch = _make_orch(tmp_path, config=old_cfg.orchestrator)
        orch._config_path = config_file  # type: ignore[attr-defined]
        orch._config_hash = "stale"  # type: ignore[attr-defined]
        orch._full_config = old_cfg  # type: ignore[attr-defined]
        orch._run_id = "prop_test"

        expected_diff = diff_configs(old_cfg, new_cfg)
        emitted: list[dict] = []

        def _capture(sink, run_id, event_type, *, payload=None, **kwargs) -> None:
            emitted.append({"event_type": event_type, "payload": payload or {}})

        with (
            patch("agent_fox.engine.config_reload.load_config", return_value=new_cfg),
            patch("agent_fox.engine.config_reload.emit_audit_event", side_effect=_capture),
        ):
            orch._reload_config()  # type: ignore[attr-defined]  # AttributeError — will fail

        config_reloaded = AuditEventType.CONFIG_RELOADED  # AttributeError — will fail
        if expected_diff:
            matching = [e for e in emitted if e["event_type"] == config_reloaded]
            assert len(matching) == 1
            assert matching[0]["payload"]["changed_fields"] == expected_diff
        else:
            assert not any(e["event_type"] == config_reloaded for e in emitted)
