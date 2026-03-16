"""Init command implementation.

Creates the .agent-fox/ directory structure, generates a default
config.toml, creates or verifies the develop branch, and updates
.gitignore with appropriate entries. Idempotent — re-running init
on an already-initialized project preserves existing configuration.

Requirements: 01-REQ-3.1, 01-REQ-3.2, 01-REQ-3.3, 01-REQ-3.4,
              01-REQ-3.5, 01-REQ-3.E1, 01-REQ-3.E2
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import click

logger = logging.getLogger(__name__)

# Template paths
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "_templates"
_AGENTS_MD_TEMPLATE = _TEMPLATES_DIR / "agents_md.md"
_SKILLS_DIR = _TEMPLATES_DIR / "skills"

# Lines to add to .gitignore
_GITIGNORE_ENTRIES = [
    "# agent-fox",
    ".agent-fox/*",
    "!.agent-fox/config.toml",
    "!.agent-fox/memory.jsonl",
    "!.agent-fox/state.jsonl",
]


def _is_git_repo() -> bool:
    """Check if the current directory is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _branch_exists(branch: str) -> bool:
    """Check if a local git branch exists."""
    result = subprocess.run(
        ["git", "branch", "--list", branch],
        capture_output=True,
        text=True,
    )
    return branch in result.stdout


def _create_branch(branch: str) -> None:
    """Create a new git branch without switching to it."""
    subprocess.run(
        ["git", "branch", branch],
        capture_output=True,
        text=True,
        check=True,
    )


def _install_skills(project_root: Path) -> int:
    """Install bundled skill templates into .claude/skills/.

    Discovers all non-hidden files in _SKILLS_DIR, creates
    {project_root}/.claude/skills/{name}/SKILL.md for each.
    Overwrites existing files.

    Args:
        project_root: The project root directory.

    Returns:
        Number of skills installed.

    Requirements: 47-REQ-2.1, 47-REQ-2.3, 47-REQ-2.4, 47-REQ-1.E1,
                  47-REQ-2.E1, 47-REQ-2.E2
    """
    # 47-REQ-2.E1: empty or missing templates dir
    if not _SKILLS_DIR.exists() or not _SKILLS_DIR.is_dir():
        logger.warning("Skills templates directory not found: %s", _SKILLS_DIR)
        return 0

    templates = [
        f for f in _SKILLS_DIR.iterdir() if f.is_file() and not f.name.startswith(".")
    ]

    if not templates:
        logger.warning("No skill templates found in %s", _SKILLS_DIR)
        return 0

    # 47-REQ-2.E2: handle permission errors creating skills directory
    skills_target = project_root / ".claude" / "skills"
    try:
        skills_target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Cannot create skills directory %s: %s", skills_target, exc)
        return 0

    count = 0
    for template_path in templates:
        name = template_path.name
        skill_dir = skills_target / name
        try:
            skill_dir.mkdir(parents=True, exist_ok=True)
            content = template_path.read_bytes()
            (skill_dir / "SKILL.md").write_bytes(content)
            count += 1
        except OSError as exc:
            # 47-REQ-1.E1: skip unreadable templates
            logger.warning("Skipping skill '%s': %s", name, exc)

    return count


def _update_gitignore(project_root: Path) -> None:
    """Add agent-fox entries to .gitignore if not already present.

    Reads the existing .gitignore (if any), appends missing entries,
    and writes the file back.
    """
    gitignore_path = project_root / ".gitignore"

    if gitignore_path.exists():
        existing = gitignore_path.read_text()
    else:
        existing = ""

    lines_to_add: list[str] = []
    for entry in _GITIGNORE_ENTRIES:
        if entry not in existing:
            lines_to_add.append(entry)

    if lines_to_add:
        # Ensure we start on a new line
        separator = "\n" if existing and not existing.endswith("\n") else ""
        addition = separator + "\n".join(lines_to_add) + "\n"
        gitignore_path.write_text(existing + addition)
        logger.debug("Updated .gitignore with agent-fox entries")


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
    agent_fox_dir = project_root / ".agent-fox"
    config_path = agent_fox_dir / "config.toml"

    # 01-REQ-3.3, 33-REQ-2.*: re-init merges existing config with schema
    if config_path.exists():
        from agent_fox.core.config_gen import merge_existing_config

        existing_content = config_path.read_text(encoding="utf-8")
        merged_content = merge_existing_config(existing_content)
        if merged_content != existing_content:
            config_path.write_text(merged_content, encoding="utf-8")
            logger.info("Config merged with current schema")
            if not json_mode:
                click.echo(
                    "Project is already initialized. "
                    "Configuration updated with new options."
                )
        else:
            if not json_mode:
                click.echo(
                    "Project is already initialized. Existing configuration preserved."
                )
        # Still ensure directory structure, seed files, and gitignore are complete
        (agent_fox_dir / "hooks").mkdir(parents=True, exist_ok=True)
        (agent_fox_dir / "worktrees").mkdir(parents=True, exist_ok=True)
        _ensure_seed_files(project_root)
        _update_gitignore(project_root)
        _ensure_develop_branch(quiet=json_mode)
        # 17-REQ-2.1: Merge canonical permissions on re-init
        _ensure_claude_settings(project_root)
        # 44-REQ-2.1, 44-REQ-3.1: Create AGENTS.md if absent
        agents_md_status = _ensure_agents_md(project_root)
        if not json_mode and agents_md_status == "created":
            click.echo("Created AGENTS.md.")
        # 47-REQ-4.2: Install skills on re-init if --skills flag set
        skills_count = None
        if skills:
            skills_count = _install_skills(project_root)
            if not json_mode:
                click.echo(f"Installed {skills_count} skills.")

        # 23-REQ-4.1: JSON output for init command
        if json_mode:
            from agent_fox.cli.json_io import emit

            result_data: dict = {"status": "ok", "agents_md": agents_md_status}
            if skills_count is not None:
                result_data["skills_installed"] = skills_count
            emit(result_data)
        return

    # 01-REQ-3.1: create directory structure
    agent_fox_dir.mkdir(parents=True, exist_ok=True)
    (agent_fox_dir / "hooks").mkdir(exist_ok=True)
    (agent_fox_dir / "worktrees").mkdir(exist_ok=True)
    logger.debug("Created .agent-fox/ directory structure")

    # 01-REQ-3.E1, 33-REQ-1.1: create default config.toml from schema
    from agent_fox.core.config_gen import generate_default_config

    config_path.write_text(generate_default_config())
    logger.debug("Created default config.toml")

    # Create seed files so they are tracked in git from the start
    _ensure_seed_files(project_root)

    # 01-REQ-3.2: create or verify develop branch
    _ensure_develop_branch(quiet=json_mode)

    # 01-REQ-3.4: update .gitignore
    _update_gitignore(project_root)

    # 17-REQ-1.1: Create Claude settings on fresh init
    _ensure_claude_settings(project_root)

    # 44-REQ-2.1: Create AGENTS.md from template on fresh init
    agents_md_status = _ensure_agents_md(project_root)

    # 47-REQ-4.1: Install skills on fresh init if --skills flag set
    skills_count = None
    if skills:
        skills_count = _install_skills(project_root)
        if not json_mode:
            click.echo(f"Installed {skills_count} skills.")

    # 23-REQ-4.1: JSON output for init command
    if json_mode:
        from agent_fox.cli.json_io import emit

        result_data_fresh: dict = {"status": "ok", "agents_md": agents_md_status}
        if skills_count is not None:
            result_data_fresh["skills_installed"] = skills_count
        emit(result_data_fresh)
    else:
        if agents_md_status == "created":
            click.echo("Created AGENTS.md.")
        click.echo("Initialized agent-fox project.")


CANONICAL_PERMISSIONS: list[str] = [
    "Bash(bash:*)",
    "Bash(wc:*)",
    "Bash(git:*)",
    "Bash(python:*)",
    "Bash(python3:*)",
    "Bash(uv:*)",
    "Bash(make:*)",
    "Bash(sort:*)",
    "Bash(awk:*)",
    "Bash(ruff:*)",
    "Bash(gh:*)",
    "Bash(claude:*)",
    "Bash(source .venv/bin/activate:*)",
    "WebSearch",
    "WebFetch(domain:pypi.org)",
    "WebFetch(domain:github.com)",
    "WebFetch(domain:raw.githubusercontent.com)",
    "Grep",
    "Read",
    "Glob",
    "Edit",
    "Write",
]


def _ensure_claude_settings(project_root: Path) -> None:
    """Create or update .claude/settings.local.json with canonical permissions.

    - If the file does not exist, create it with CANONICAL_PERMISSIONS.
    - If the file exists, merge: add missing canonical entries, preserve
      user-added entries and their ordering.
    - If the file contains invalid JSON, log a warning and skip.

    Requirements: 17-REQ-1.1, 17-REQ-1.2, 17-REQ-1.3, 17-REQ-1.E1,
                  17-REQ-2.1, 17-REQ-2.2, 17-REQ-2.3,
                  17-REQ-2.E1, 17-REQ-2.E2, 17-REQ-2.E3
    """
    claude_dir = project_root / ".claude"
    settings_path = claude_dir / "settings.local.json"

    # 17-REQ-1.2: Create .claude/ directory if absent
    claude_dir.mkdir(parents=True, exist_ok=True)

    if not settings_path.exists():
        # 17-REQ-1.1: Create with canonical permissions
        data = {"permissions": {"allow": list(CANONICAL_PERMISSIONS)}}
        settings_path.write_text(json.dumps(data, indent=2) + "\n")
        logger.debug("Created .claude/settings.local.json")
        return

    # File exists — merge
    raw = settings_path.read_text()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # 17-REQ-2.E1: Invalid JSON — warn and skip
        logger.warning(
            "Invalid JSON in %s, skipping settings merge",
            settings_path,
        )
        return

    if not isinstance(data, dict):
        logger.warning("Settings file is not a JSON object, skipping merge")
        return

    # 17-REQ-2.E2: Missing permissions structure — create it
    if "permissions" not in data:
        data["permissions"] = {}
    permissions = data["permissions"]

    if not isinstance(permissions, dict):
        logger.warning("permissions is not a JSON object, skipping merge")
        return

    if "allow" not in permissions:
        permissions["allow"] = []

    allow = permissions["allow"]
    if not isinstance(allow, list):
        # 17-REQ-2.E3: allow is not a list — warn and skip
        logger.warning("permissions.allow is not a list, skipping merge")
        return

    # 17-REQ-2.1, 17-REQ-2.2, 17-REQ-2.3: Merge
    existing_set = set(allow)
    missing = [p for p in CANONICAL_PERMISSIONS if p not in existing_set]

    if not missing:
        # 17-REQ-1.E1: All canonical entries present — no-op
        logger.debug("All canonical permissions already present")
        return

    # Preserve order: existing first, new appended
    allow.extend(missing)
    settings_path.write_text(json.dumps(data, indent=2) + "\n")
    logger.debug(
        "Merged %d missing canonical permissions into settings",
        len(missing),
    )


_DOCS_MEMORY_CONTENT = "# Agent-Fox Memory\n\n_No facts have been recorded yet._\n"


def _ensure_seed_files(project_root: Path) -> None:
    """Create empty seed files so they are tracked in git from the start.

    Creates .agent-fox/memory.jsonl, .agent-fox/state.jsonl, and
    docs/memory.md if they do not already exist. Idempotent — existing
    files are never overwritten.
    """
    agent_fox_dir = project_root / ".agent-fox"

    for name in ("memory.jsonl", "state.jsonl"):
        path = agent_fox_dir / name
        if not path.exists():
            path.touch()
            logger.debug("Created seed file %s", path)

    docs_dir = project_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    docs_memory = docs_dir / "memory.md"
    if not docs_memory.exists():
        docs_memory.write_text(_DOCS_MEMORY_CONTENT, encoding="utf-8")
        logger.debug("Created docs/memory.md")


def _ensure_agents_md(project_root: Path) -> str:
    """Create AGENTS.md from template if it does not exist.

    Args:
        project_root: The project root directory (Path.cwd()).

    Returns:
        "created" if the file was written, "skipped" if it already existed.

    Raises:
        FileNotFoundError: If the bundled template is missing.

    Requirements: 44-REQ-1.E1, 44-REQ-2.1, 44-REQ-3.1, 44-REQ-3.E1
    """
    agents_md = project_root / "AGENTS.md"
    if agents_md.exists():
        return "skipped"

    # This raises FileNotFoundError if the template is missing (44-REQ-1.E1)
    content = _AGENTS_MD_TEMPLATE.read_text(encoding="utf-8")
    agents_md.write_text(content, encoding="utf-8")
    logger.debug("Created AGENTS.md from template")
    return "created"


def _ensure_develop_branch(*, quiet: bool = False) -> None:
    """Create or recover the develop branch using the robust ensure logic.

    Uses the async ``ensure_develop()`` from workspace.git, which handles
    remote tracking, fast-forwarding, and fallback to the default branch.

    Args:
        quiet: If True, suppress human-readable output (for JSON mode).

    Requirements: 19-REQ-1.5
    """
    import asyncio

    from agent_fox.workspace.workspace import ensure_develop

    try:
        asyncio.run(ensure_develop(Path.cwd()))
        if not quiet:
            click.echo("Branch 'develop' is ready.")
    except Exception as exc:
        if not quiet:
            click.echo(f"Warning: Could not ensure develop branch: {exc}", err=True)
        # Fall back to the simple approach
        if _branch_exists("develop"):
            if not quiet:
                click.echo("Branch 'develop' already exists.")
        else:
            try:
                _create_branch("develop")
                if not quiet:
                    click.echo("Created branch 'develop'.")
            except Exception:
                if not quiet:
                    click.echo("Error: Could not create develop branch.", err=True)
