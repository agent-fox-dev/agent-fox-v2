"""Fixtures for hook and security tests.

Provides temporary executable hook scripts, default HookContext and
HookConfig, and temporary .specs/ directories for hot-load tests.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from agent_fox.core.config import HookConfig, SecurityConfig
from agent_fox.hooks.hooks import HookContext


@pytest.fixture
def hook_context(tmp_path: Path) -> HookContext:
    """Default HookContext for testing."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return HookContext(
        spec_name="03_session",
        task_group="2",
        workspace=str(workspace),
        branch="feature/03_session/2",
    )


@pytest.fixture
def hook_config() -> HookConfig:
    """Default HookConfig with no hooks configured."""
    return HookConfig()


@pytest.fixture
def tmp_hook_script(tmp_path: Path):
    """Factory fixture: creates temporary executable shell scripts.

    Usage:
        script = tmp_hook_script("#!/bin/sh\\nexit 0\\n")
        script = tmp_hook_script("#!/bin/sh\\nexit 1\\n", name="failing.sh")
    """

    def _create(content: str, *, name: str = "hook.sh") -> str:
        script_path = tmp_path / name
        script_path.write_text(content)
        # Make executable
        st = os.stat(script_path)
        os.chmod(script_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return str(script_path)

    return _create


@pytest.fixture
def marker_file(tmp_path: Path) -> Path:
    """Provide a path to a marker file for hook output verification."""
    return tmp_path / "marker.txt"


@pytest.fixture
def security_config() -> SecurityConfig:
    """Default SecurityConfig for testing."""
    return SecurityConfig()


@pytest.fixture
def tmp_specs_dir(tmp_path: Path) -> Path:
    """Create a temporary .specs/ directory for hot-load tests."""
    specs_dir = tmp_path / ".specs"
    specs_dir.mkdir()
    return specs_dir
