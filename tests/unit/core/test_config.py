"""Configuration system tests.

Test Spec: TS-01-3 (defaults), TS-01-4 (overrides), TS-01-5 (invalid type),
           TS-01-E2 (missing file), TS-01-E3 (invalid TOML), TS-01-E7 (unknown keys)
Requirements: 01-REQ-2.1, 01-REQ-2.2, 01-REQ-2.3, 01-REQ-2.6, 01-REQ-2.E1,
              01-REQ-2.E2
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.core.config import AgentFoxConfig, load_config
from agent_fox.core.errors import ConfigError


class TestConfigDefaults:
    """TS-01-3: Config loads defaults from empty TOML."""

    def test_empty_toml_returns_defaults(self, tmp_path: Path) -> None:
        """An empty config file produces all default values."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("")

        config = load_config(path=config_file)

        assert isinstance(config, AgentFoxConfig)
        assert config.orchestrator.parallel == 1
        assert config.orchestrator.sync_interval == 5
        assert config.orchestrator.max_retries == 2
        assert config.orchestrator.session_timeout == 30
        assert config.theme.playful is True
        assert config.models.coding == "ADVANCED"

    def test_whitespace_only_toml_returns_defaults(self, tmp_path: Path) -> None:
        """A whitespace-only config file produces all default values."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("   \n\n  \n")

        config = load_config(path=config_file)

        assert config.orchestrator.parallel == 1
        assert config.models.coding == "ADVANCED"


class TestConfigOverrides:
    """TS-01-4: Config loads overrides from TOML."""

    def test_toml_override_applied(self, tmp_path: Path) -> None:
        """Values in TOML override defaults."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[orchestrator]\nparallel = 4\n")

        config = load_config(path=config_file)

        assert config.orchestrator.parallel == 4
        # Other fields remain at defaults
        assert config.orchestrator.sync_interval == 5

    def test_multiple_overrides(self, tmp_path: Path) -> None:
        """Multiple overrides are all applied."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "[orchestrator]\n"
            "parallel = 4\n"
            "sync_interval = 10\n"
            "\n"
            "[theme]\n"
            "playful = false\n"
        )

        config = load_config(path=config_file)

        assert config.orchestrator.parallel == 4
        assert config.orchestrator.sync_interval == 10
        assert config.theme.playful is False


class TestConfigInvalidType:
    """TS-01-5: Config rejects invalid type."""

    def test_string_for_int_raises_config_error(self, tmp_path: Path) -> None:
        """A string where an int is expected raises ConfigError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[orchestrator]\nparallel = "not_a_number"\n')

        with pytest.raises(ConfigError) as exc_info:
            load_config(path=config_file)

        assert "parallel" in str(exc_info.value).lower()


class TestConfigMissingFile:
    """TS-01-E2: Config file missing returns defaults."""

    def test_nonexistent_file_returns_defaults(self) -> None:
        """A non-existent config path returns all defaults without error."""
        config = load_config(path=Path("/tmp/nonexistent_config_12345.toml"))

        assert isinstance(config, AgentFoxConfig)
        assert config.orchestrator.parallel == 1
        assert config.models.coding == "ADVANCED"


class TestConfigInvalidTOML:
    """TS-01-E3: Config file invalid TOML raises ConfigError."""

    def test_broken_toml_raises_config_error(self, tmp_path: Path) -> None:
        """Malformed TOML raises ConfigError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[broken toml }{")

        with pytest.raises(ConfigError):
            load_config(path=config_file)


class TestConfigUnrecognizedKeys:
    """TS-01-E7: Unrecognized config keys are ignored."""

    def test_unknown_section_ignored(self, tmp_path: Path) -> None:
        """Unknown keys in TOML are silently ignored."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[unknown_section]\nfoo = "bar"\n')

        config = load_config(path=config_file)

        assert isinstance(config, AgentFoxConfig)
        assert config.orchestrator.parallel == 1  # defaults applied

    def test_unknown_field_in_known_section_ignored(self, tmp_path: Path) -> None:
        """Unknown fields within known sections are silently ignored."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "[orchestrator]\nparallel = 2\ntotally_unknown_field = 42\n"
        )

        config = load_config(path=config_file)

        assert config.orchestrator.parallel == 2
