"""Tests asserting the hook runner and HookConfig are removed.

Test Spec: TS-103-1, TS-103-2, TS-103-3, TS-103-7
Requirements: 103-REQ-1.2, 103-REQ-1.3, 103-REQ-1.E1, 103-REQ-4.3
"""

from __future__ import annotations

from pathlib import Path

import agent_fox.core.errors as errors
from agent_fox.core.config import AgentFoxConfig, load_config


class TestHookConfigAbsent:
    """TS-103-1: HookConfig must not exist as a field on AgentFoxConfig."""

    def test_hooks_field_absent_from_agent_fox_config(self) -> None:
        """AgentFoxConfig.model_fields must not contain 'hooks'."""
        assert "hooks" not in AgentFoxConfig.model_fields


class TestHookErrorAbsent:
    """TS-103-2: HookError must not be defined in errors.py."""

    def test_hook_error_absent_from_errors_module(self) -> None:
        """errors module must not have HookError attribute."""
        assert not hasattr(errors, "HookError")


class TestTomlHooksIgnored:
    """TS-103-3: TOML with [hooks] section must parse successfully."""

    def test_toml_with_hooks_section_parses_successfully(self, tmp_path: Path) -> None:
        """load_config() with a [hooks] section returns AgentFoxConfig without error."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[hooks]\npre_code = ["echo hello"]\ntimeout = 60\n',
            encoding="utf-8",
        )
        config = load_config(config_file)
        assert isinstance(config, AgentFoxConfig)


class TestConfigGenNoHookConfig:
    """TS-103-7: config_gen.py must not contain any HookConfig references."""

    def test_config_gen_has_no_hookconfig_references(self) -> None:
        """config_gen.py must not contain the string 'HookConfig'."""
        config_gen_path = Path(__file__).parent.parent.parent.parent / "agent_fox" / "core" / "config_gen.py"
        content = config_gen_path.read_text(encoding="utf-8")
        assert "HookConfig" not in content
