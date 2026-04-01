"""Integration tests for config simplification.

Test Spec: TS-68-11
Requirements: 68-REQ-1.5
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.core.config import load_config
from agent_fox.core.config_gen import generate_default_config


class TestHiddenSectionsLoad:
    """TS-68-11: Manually-added hidden sections load correctly."""

    def test_routing_and_theme_load_correctly(self, tmp_path: Path):
        """Config with routing and theme sections appended loads without error."""
        base = generate_default_config()
        extra = (
            "\n[routing]\nretries_before_escalation = 2\n\n[theme]\nplayful = false\n"
        )
        content = base + extra
        config_file = tmp_path / "config.toml"
        config_file.write_text(content)

        config = load_config(config_file)

        assert config.routing.retries_before_escalation == 2, (
            f"routing.retries_before_escalation is "
            f"{config.routing.retries_before_escalation}, expected 2"
        )
        assert config.theme.playful is False, (
            f"theme.playful is {config.theme.playful}, expected False"
        )

    def test_knowledge_hidden_section_loads(self, tmp_path: Path):
        """Config with knowledge section appended loads correctly."""
        base = generate_default_config()
        extra = "\n[knowledge]\nask_top_k = 50\n"
        content = base + extra
        config_file = tmp_path / "config.toml"
        config_file.write_text(content)

        config = load_config(config_file)

        assert config.knowledge.ask_top_k == 50, (
            f"knowledge.ask_top_k is {config.knowledge.ask_top_k}, expected 50"
        )

    def test_multiple_hidden_sections_load(self, tmp_path: Path):
        """Config with multiple hidden sections all load correctly."""
        base = generate_default_config()
        extra = (
            "\n[routing]\n"
            "retries_before_escalation = 1\n"
            "\n[theme]\n"
            "playful = true\n"
            "\n[knowledge]\n"
            "ask_top_k = 10\n"
        )
        content = base + extra
        config_file = tmp_path / "config.toml"
        config_file.write_text(content)

        config = load_config(config_file)

        assert config.routing.retries_before_escalation == 1
        assert config.theme.playful is True
        assert config.knowledge.ask_top_k == 10
