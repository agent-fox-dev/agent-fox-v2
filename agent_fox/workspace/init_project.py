"""Backing module for the ``init`` CLI command.

Provides ``init_project()`` as a callable entry point for project
initialization, usable without the Click framework.

Requirements: 59-REQ-5.1, 59-REQ-5.2, 59-REQ-5.3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InitResult:
    """Structured result from project initialization."""

    status: str  # "ok" | "already_initialized"
    agents_md: str  # "created" | "skipped"
    skills_installed: int = 0


def init_project(
    path: Path,
    *,
    force: bool = False,
    skills: bool = False,
) -> InitResult:
    """Initialize agent-fox in a project directory.

    This function can be called without the Click framework.

    Args:
        path: Project root directory.
        force: Force re-initialization even if already set up.
        skills: Install bundled Claude Code skills.

    Returns:
        InitResult with initialization status.

    Requirements: 59-REQ-5.1, 59-REQ-5.2, 59-REQ-5.3
    """
    from agent_fox.cli.init import (
        _ensure_agents_md,
        _ensure_claude_settings,
        _ensure_develop_branch,
        _ensure_seed_files,
        _install_skills,
        _secure_mkdir,
        _secure_write_text,
        _update_gitignore,
    )

    agent_fox_dir = path / ".agent-fox"
    config_path = agent_fox_dir / "config.toml"

    already_initialized = config_path.exists()

    if already_initialized and not force:
        # Re-init: merge existing config with schema
        from agent_fox.core.config_gen import merge_existing_config

        existing_content = config_path.read_text(encoding="utf-8")
        merged_content = merge_existing_config(existing_content)
        if merged_content != existing_content:
            config_path.write_text(merged_content, encoding="utf-8")

        # Ensure structure is complete
        (agent_fox_dir / "hooks").mkdir(parents=True, exist_ok=True)
        (agent_fox_dir / "worktrees").mkdir(parents=True, exist_ok=True)
        _ensure_seed_files(path)
        _update_gitignore(path)
        _ensure_develop_branch(quiet=True)
        _ensure_claude_settings(path)
        agents_md_status = _ensure_agents_md(path)

        skills_count = 0
        if skills:
            skills_count = _install_skills(path)

        return InitResult(
            status="already_initialized",
            agents_md=agents_md_status,
            skills_installed=skills_count,
        )

    # Fresh initialization
    _secure_mkdir(agent_fox_dir)
    (agent_fox_dir / "hooks").mkdir(exist_ok=True)
    (agent_fox_dir / "worktrees").mkdir(exist_ok=True)

    from agent_fox.core.config_gen import generate_default_config

    _secure_write_text(config_path, generate_default_config())

    _ensure_seed_files(path)
    _ensure_develop_branch(quiet=True)
    _update_gitignore(path)
    _ensure_claude_settings(path)
    agents_md_status = _ensure_agents_md(path)

    skills_count = 0
    if skills:
        skills_count = _install_skills(path)

    return InitResult(
        status="ok",
        agents_md=agents_md_status,
        skills_installed=skills_count,
    )
