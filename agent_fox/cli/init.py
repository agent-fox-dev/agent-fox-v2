"""Init CLI command: initialize an agent-fox project.

Thin CLI wrapper that delegates to ``workspace.init_project`` for
all initialization logic, then handles output formatting.

Requirements: 01-REQ-3.1, 01-REQ-3.2, 01-REQ-3.3, 01-REQ-3.4,
              01-REQ-3.5, 01-REQ-3.E1, 01-REQ-3.E2
"""

from __future__ import annotations

from pathlib import Path

import click

from agent_fox.workspace.init_project import (
    _is_git_repo,
    init_project,
)


@click.command("init")
@click.option(
    "--skills",
    is_flag=True,
    default=False,
    help="Install bundled Claude Code skills into .claude/skills/.",
)
@click.pass_context
def init_cmd(ctx: click.Context, skills: bool) -> None:
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
