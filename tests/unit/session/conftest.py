"""Fixtures for session tests: spec directories, mocks, configs."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.workspace.worktree import WorkspaceInfo


@pytest.fixture
def tmp_spec_dir(tmp_path: Path) -> Path:
    """Create a temporary spec directory with sample spec files.

    Contains requirements.md, design.md, and tasks.md with known content.
    """
    spec_dir = tmp_path / "specs" / "test_spec"
    spec_dir.mkdir(parents=True)

    (spec_dir / "requirements.md").write_text("# Requirements\nREQ content here\n")
    (spec_dir / "design.md").write_text("# Design\nDesign content here\n")
    (spec_dir / "tasks.md").write_text("# Tasks\nTask content here\n")

    return spec_dir


@pytest.fixture
def default_config() -> AgentFoxConfig:
    """Provide an AgentFoxConfig with test-friendly defaults."""
    return AgentFoxConfig()


@pytest.fixture
def short_timeout_config() -> AgentFoxConfig:
    """Provide an AgentFoxConfig with a very short session timeout.

    Uses 1 minute timeout for testing.
    """
    return AgentFoxConfig(
        orchestrator={"session_timeout": 1},  # type: ignore[arg-type]
    )


@pytest.fixture
def small_allowlist_config() -> AgentFoxConfig:
    """Provide an AgentFoxConfig with a restricted allowlist.

    Only allows 'git' and 'python' commands.
    """
    return AgentFoxConfig(
        security={"bash_allowlist": ["git", "python"]},  # type: ignore[arg-type]
    )


@pytest.fixture
def workspace_info(tmp_path: Path) -> WorkspaceInfo:
    """Provide a WorkspaceInfo pointing to a temp directory."""
    ws_path = tmp_path / "worktree"
    ws_path.mkdir()
    return WorkspaceInfo(
        path=ws_path,
        branch="feature/test_spec/1",
        spec_name="test_spec",
        task_group=1,
    )
