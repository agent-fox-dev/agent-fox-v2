"""Configuration tests for tools section.

Test Spec: TS-29-26 (default false), TS-29-27 (tools enabled),
           TS-29-28 (tools disabled), TS-29-E18 (invalid value)
Requirements: 29-REQ-8.1, 29-REQ-8.2, 29-REQ-8.3, 29-REQ-8.E1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.core.config import AgentFoxConfig, load_config
from agent_fox.core.errors import ConfigError


class TestConfigDefaultFalse:
    """TS-29-26: Default config has fox_tools=false."""

    def test_default_false(self) -> None:
        config = AgentFoxConfig()
        assert config.tools.fox_tools is False


class TestConfigToolsEnabled:
    """TS-29-27: Session runner constructs ToolDefinitions when fox_tools=true."""

    def test_tools_enabled(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("[tools]\nfox_tools = true\n")
        config = load_config(config_file)
        assert config.tools.fox_tools is True

        # Verify build_fox_tool_definitions returns 4 definitions
        from agent_fox.tools.registry import build_fox_tool_definitions

        defs = build_fox_tool_definitions()
        assert len(defs) == 4
        assert {d.name for d in defs} == {
            "fox_outline",
            "fox_read",
            "fox_edit",
            "fox_search",
        }


class TestConfigToolsDisabled:
    """TS-29-28: No tools passed when fox_tools=false."""

    def test_tools_disabled(self) -> None:
        config = AgentFoxConfig()
        assert config.tools.fox_tools is False


class TestConfigInvalidValue:
    """TS-29-E18: ConfigError for invalid fox_tools value."""

    def test_invalid_value(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[tools]\nfox_tools = "yes"\n')
        with pytest.raises(ConfigError) as exc:
            load_config(config_file)
        assert "fox_tools" in str(exc.value)
