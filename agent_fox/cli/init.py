"""Init CLI command: initialize an agent-fox project.

Thin CLI wrapper that delegates to ``workspace.init_project`` for
all initialization logic, then handles output formatting.

Requirements: 01-REQ-3.1, 01-REQ-3.2, 01-REQ-3.3, 01-REQ-3.4,
              01-REQ-3.5, 01-REQ-3.E1, 01-REQ-3.E2,
              99-REQ-3.1, 99-REQ-3.2, 99-REQ-3.3, 99-REQ-3.E1
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import click

from agent_fox.workspace.init_project import (
    _is_git_repo,
    init_project,
)

logger = logging.getLogger(__name__)

# Package-embedded default profiles directory (mirrors profiles.py resolution)
_DEFAULT_PROFILES_DIR: Path = (
    Path(__file__).resolve().parent.parent / "_templates" / "profiles"
)


def init_profiles(project_dir: Path) -> list[Path]:
    """Copy default archetype profiles into ``.agent-fox/profiles/``.

    Copies all ``*.md`` files from the package-embedded
    ``_templates/profiles/`` directory into
    ``<project_dir>/.agent-fox/profiles/``.  Existing files are skipped
    without modification.  The destination directory is created if absent.

    Args:
        project_dir: Root of the project directory.

    Returns:
        List of newly created profile file paths.  Files that already
        existed are not included.

    Requirements: 99-REQ-3.1, 99-REQ-3.2, 99-REQ-3.3, 99-REQ-3.E1
    """
    profiles_dest = project_dir / ".agent-fox" / "profiles"
    profiles_dest.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    for src_file in sorted(_DEFAULT_PROFILES_DIR.glob("*.md")):
        dest_file = profiles_dest / src_file.name
        if dest_file.exists():
            logger.debug("Preserving existing profile: %s", dest_file)
            continue
        shutil.copy2(src_file, dest_file)
        created.append(dest_file)

    return created


@click.command("init")
@click.option(
    "--skills",
    is_flag=True,
    default=False,
    help="Install bundled Claude Code skills into .claude/skills/.",
)
@click.option(
    "--profiles",
    is_flag=True,
    default=False,
    help="Copy default archetype profiles into .agent-fox/profiles/.",
)
@click.pass_context
def init_cmd(ctx: click.Context, skills: bool, profiles: bool) -> None:
    """Initialize the current project for agent-fox.

    Creates the .agent-fox/ directory structure with a default
    configuration file, sets up the development branch, and
    updates .gitignore.
    """
    json_mode = ctx.obj.get("json", False)

    # 01-REQ-3.5: check we are in a git repository
    if not _is_git_repo():
        if json_mode:
            from agent_fox.cli.json_io import emit_error

            emit_error("Not inside a git repository. Run 'git init' first.")
            ctx.exit(1)
            return
        click.echo(
            "Error: Not inside a git repository. Run 'git init' first.",
            err=True,
        )
        ctx.exit(1)
        return

    project_root = Path.cwd()
    config_path = project_root / ".agent-fox" / "config.toml"
    already_initialized = config_path.exists()

    result = init_project(project_root, skills=skills, quiet=json_mode)

    # 23-REQ-4.1: JSON output for init command
    if json_mode:
        from agent_fox.cli.json_io import emit

        result_data: dict = {
            "status": "ok",
            "agents_md": result.agents_md,
            "steering_md": result.steering_md,
        }
        if result.skills_installed:
            result_data["skills_installed"] = result.skills_installed
        emit(result_data)
        return

    # Text output
    if already_initialized:
        from agent_fox.core.config_gen import merge_existing_config

        existing_content = config_path.read_text(encoding="utf-8")
        merged_content = merge_existing_config(existing_content)
        if merged_content != existing_content:
            click.echo("Project is already initialized. Configuration updated with new options.")
        else:
            click.echo("Project is already initialized. Existing configuration preserved.")
    else:
        click.echo("Initialized agent-fox project.")

    if result.agents_md == "created":
        click.echo("Created AGENTS.md.")
    if result.steering_md == "created":
        click.echo("Created .specs/steering.md.")
    if result.skills_installed:
        click.echo(f"Installed {result.skills_installed} skills.")
    if profiles:
        created_profiles = init_profiles(project_root)
        if created_profiles:
            click.echo(f"Installed {len(created_profiles)} archetype profiles.")
        else:
            click.echo("All archetype profiles already exist; nothing to install.")
