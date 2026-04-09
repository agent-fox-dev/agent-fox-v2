"""Shared fixtures for model routing tests.

Provides config.toml helpers used by test_config.py and test_escalation.py.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def minimal_config_toml(tmp_path: Path) -> Path:
    """Create a minimal config.toml with no [routing] section."""
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent("""\
    [orchestrator]
    parallel = 1
    """)
    )
    return p


@pytest.fixture
def routing_config_toml(tmp_path: Path) -> Path:
    """Create a config.toml with [routing] section."""
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent("""\
    [orchestrator]
    parallel = 1

    [routing]
    retries_before_escalation = 2
    """)
    )
    return p


@pytest.fixture
def extreme_routing_config_toml(tmp_path: Path) -> Path:
    """Create a config.toml with out-of-range [routing] values."""
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent("""\
    [routing]
    retries_before_escalation = 10
    """)
    )
    return p


@pytest.fixture
def bad_type_routing_config_toml(tmp_path: Path) -> Path:
    """Create a config.toml with invalid type in [routing]."""
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent("""\
    [routing]
    retries_before_escalation = "high"
    """)
    )
    return p


@pytest.fixture
def archetype_ceiling_config_toml(tmp_path: Path) -> Path:
    """Create a config.toml with archetype model override."""
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent("""\
    [archetypes]
    models = { coder = "STANDARD" }
    """)
    )
    return p
