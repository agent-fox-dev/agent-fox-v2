"""Property tests for configuration system.

Test Spec: TS-01-P1 (defaults completeness), TS-01-P2 (numeric clamping)
Properties: Property 1, Property 8 from design.md
Requirements: 01-REQ-2.1, 01-REQ-2.3, 01-REQ-2.E3
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import AgentFoxConfig, load_config


class TestConfigDefaultsCompleteness:
    """TS-01-P1: Config defaults completeness.

    Property 1: For any valid but empty TOML file, load_config() returns an
    AgentFoxConfig instance where every field has its documented default value.
    """

    @given(whitespace=st.text(alphabet=" \t\n\r", max_size=50))
    @settings(max_examples=20)
    def test_whitespace_toml_produces_defaults(self, tmp_path_factory: pytest.TempPathFactory, whitespace: str) -> None:
        """Any whitespace-only TOML produces all documented defaults."""
        tmp_dir = tmp_path_factory.mktemp("config")
        config_file = tmp_dir / "config.toml"
        config_file.write_text(whitespace)

        config = load_config(path=config_file)

        assert isinstance(config, AgentFoxConfig)
        assert config.orchestrator.parallel == 2
        assert config.orchestrator.sync_interval == 5
        assert config.orchestrator.max_retries == 2
        assert config.orchestrator.session_timeout == 30
        assert config.orchestrator.hot_load is True
        assert config.orchestrator.inter_session_delay == 3
        assert config.orchestrator.max_cost is None
        assert config.orchestrator.max_sessions is None
        assert config.theme.playful is True
        assert config.theme.header == "bold #ff8c00"
        assert config.theme.success == "bold green"
        assert config.theme.error == "bold red"
        assert config.theme.warning == "bold yellow"
        assert config.theme.info == "#daa520"
        assert config.theme.tool == "bold #cd853f"
        assert config.theme.muted == "dim"
        assert config.models.coding == "ADVANCED"
        assert config.models.memory_extraction == "SIMPLE"


class TestConfigNumericClamping:
    """TS-01-P2: Config numeric clamping.

    Property 8: For any numeric configuration value outside its valid range,
    load_config() clamps it to the nearest valid bound rather than rejecting.
    """

    @given(n=st.integers(min_value=-1000, max_value=1000))
    @settings(max_examples=50)
    def test_parallel_clamped_to_valid_range(self, tmp_path_factory: pytest.TempPathFactory, n: int) -> None:
        """orchestrator.parallel is always clamped to [1, 8]."""
        tmp_dir = tmp_path_factory.mktemp("config")
        config_file = tmp_dir / "config.toml"
        config_file.write_text(f"[orchestrator]\nparallel = {n}\n")

        config = load_config(path=config_file)

        assert 1 <= config.orchestrator.parallel <= 8

    @given(n=st.integers(min_value=-1000, max_value=1000))
    @settings(max_examples=50)
    def test_sync_interval_clamped_to_valid_range(self, tmp_path_factory: pytest.TempPathFactory, n: int) -> None:
        """orchestrator.sync_interval is always clamped to >= 0."""
        tmp_dir = tmp_path_factory.mktemp("config")
        config_file = tmp_dir / "config.toml"
        config_file.write_text(f"[orchestrator]\nsync_interval = {n}\n")

        config = load_config(path=config_file)

        assert config.orchestrator.sync_interval >= 0

    @given(n=st.integers(min_value=-1000, max_value=1000))
    @settings(max_examples=50)
    def test_session_timeout_clamped_to_valid_range(self, tmp_path_factory: pytest.TempPathFactory, n: int) -> None:
        """orchestrator.session_timeout is always clamped to >= 1."""
        tmp_dir = tmp_path_factory.mktemp("config")
        config_file = tmp_dir / "config.toml"
        config_file.write_text(f"[orchestrator]\nsession_timeout = {n}\n")

        config = load_config(path=config_file)

        assert config.orchestrator.session_timeout >= 1
