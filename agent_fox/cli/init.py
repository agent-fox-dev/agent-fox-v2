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

# Default config.toml template with all sections commented out
_DEFAULT_CONFIG = """\
# agent-fox configuration
# See documentation for all available settings.

# [orchestrator]
# parallel = 1
# sync_interval = 5
# session_timeout = 30
# max_retries = 2

# [models]
# coding = "ADVANCED"
# coordinator = "STANDARD"
# memory_extraction = "SIMPLE"

# [theme]
# playful = true

# [platform]
# type = "none"
"""

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
@click.pass_context
def init_cmd(ctx: click.Context) -> None:
    """Initialize the current project for agent-fox.

    Creates the .agent-fox/ directory structure with a default
    configuration file, sets up the development branch, and
    updates .gitignore.
    """
    # 01-REQ-3.5: check we are in a git repository
    if not _is_git_repo():
        click.echo(
            "Error: Not inside a git repository. Run 'git init' first.",
            err=True,
        )
        ctx.exit(1)
        return

    project_root = Path.cwd()
    agent_fox_dir = project_root / ".agent-fox"
    config_path = agent_fox_dir / "config.toml"

    # 01-REQ-3.3: idempotency — preserve existing config
    if config_path.exists():
        click.echo("Project is already initialized. Existing configuration preserved.")
        # Still ensure directory structure and gitignore are complete
        (agent_fox_dir / "hooks").mkdir(parents=True, exist_ok=True)
        (agent_fox_dir / "worktrees").mkdir(parents=True, exist_ok=True)
        _update_gitignore(project_root)
        _ensure_develop_branch()
        # 17-REQ-2.1: Merge canonical permissions on re-init
        _ensure_claude_settings(project_root)
        return

    # 01-REQ-3.1: create directory structure
    agent_fox_dir.mkdir(parents=True, exist_ok=True)
    (agent_fox_dir / "hooks").mkdir(exist_ok=True)
    (agent_fox_dir / "worktrees").mkdir(exist_ok=True)
    logger.debug("Created .agent-fox/ directory structure")

    # 01-REQ-3.E1: create default config.toml
    config_path.write_text(_DEFAULT_CONFIG)
    logger.debug("Created default config.toml")

    # 01-REQ-3.2: create or verify develop branch
    _ensure_develop_branch()

    # 01-REQ-3.4: update .gitignore
    _update_gitignore(project_root)

    # 17-REQ-1.1: Create Claude settings on fresh init
    _ensure_claude_settings(project_root)

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


def _ensure_develop_branch() -> None:
    """Create or recover the develop branch using the robust ensure logic.

    Uses the async ``ensure_develop()`` from workspace.git, which handles
    remote tracking, fast-forwarding, and fallback to the default branch.

    Requirements: 19-REQ-1.5
    """
    import asyncio

    from agent_fox.workspace.git import ensure_develop

    try:
        asyncio.run(ensure_develop(Path.cwd()))
        click.echo("Branch 'develop' is ready.")
    except Exception as exc:
        click.echo(f"Warning: Could not ensure develop branch: {exc}", err=True)
        # Fall back to the simple approach
        if _branch_exists("develop"):
            click.echo("Branch 'develop' already exists.")
        else:
            try:
                _create_branch("develop")
                click.echo("Created branch 'develop'.")
            except Exception:
                click.echo(
                    "Error: Could not create develop branch.", err=True
                )
