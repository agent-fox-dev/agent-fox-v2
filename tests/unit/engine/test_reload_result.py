"""Tests for ReloadResult dataclass and ConfigReloader.reload() return type.

Test Spec: TS-103-5, TS-103-6
Requirements: 103-REQ-3.1, 103-REQ-3.2, 103-REQ-3.3
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from agent_fox.core.config import OrchestratorConfig
from agent_fox.engine.circuit import CircuitBreaker
from agent_fox.engine.engine import ConfigReloader, ReloadResult


class TestReloadResultDataclassFields:
    """TS-103-5: ReloadResult must have exactly four named fields."""

    def test_reload_result_has_expected_fields(self) -> None:
        """ReloadResult dataclass must expose config, circuit, archetypes, planning."""
        field_names = {f.name for f in dataclasses.fields(ReloadResult)}
        assert field_names == {"config", "circuit", "archetypes", "planning"}

    def test_reload_result_is_frozen(self) -> None:
        """ReloadResult must be a frozen dataclass (immutable)."""
        assert ReloadResult.__dataclass_params__.frozen  # type: ignore[attr-defined]


class TestConfigReloaderReturnsReloadResult:
    """TS-103-6: ConfigReloader.reload() must return a ReloadResult on success."""

    def test_reload_returns_reload_result_instance(self, tmp_path: Path) -> None:
        """reload() returns a ReloadResult instance, not a raw tuple."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("", encoding="utf-8")  # valid empty TOML

        reloader = ConfigReloader(config_path=config_file, full_config=None)
        current_cfg = OrchestratorConfig(parallel=1, inter_session_delay=0)
        circuit = CircuitBreaker(current_cfg)

        result = reloader.reload(
            current_config=current_cfg,
            circuit=circuit,
            sink=None,
            run_id="test-run",
        )

        assert isinstance(result, ReloadResult)

    def test_reload_result_exposes_all_fields(self, tmp_path: Path) -> None:
        """Successful reload result exposes config, circuit, archetypes, planning."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("", encoding="utf-8")

        reloader = ConfigReloader(config_path=config_file, full_config=None)
        current_cfg = OrchestratorConfig(parallel=1, inter_session_delay=0)
        circuit = CircuitBreaker(current_cfg)

        result = reloader.reload(
            current_config=current_cfg,
            circuit=circuit,
            sink=None,
            run_id="test-run",
        )

        assert result is not None
        assert hasattr(result, "config")
        assert hasattr(result, "circuit")
        assert hasattr(result, "archetypes")
        assert hasattr(result, "planning")

    def test_reload_none_when_no_config_path(self) -> None:
        """reload() returns None when config_path is None (103-REQ-3.3)."""
        reloader = ConfigReloader(config_path=None, full_config=None)
        current_cfg = OrchestratorConfig(parallel=1, inter_session_delay=0)
        circuit = CircuitBreaker(current_cfg)

        result = reloader.reload(
            current_config=current_cfg,
            circuit=circuit,
            sink=None,
            run_id="test-run",
        )

        assert result is None
