"""Init command implementation.

Creates the .agent-fox/ directory structure, generates a default
config.toml, creates or verifies the develop branch, and updates
.gitignore with appropriate entries. Idempotent — re-running init
on an already-initialized project preserves existing configuration.

Requirements: 01-REQ-3.1, 01-REQ-3.2, 01-REQ-3.3, 01-REQ-3.4,
              01-REQ-3.5, 01-REQ-3.E1, 01-REQ-3.E2
"""

from __future__ import annotations

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

    click.echo("Initialized agent-fox project.")


def _ensure_develop_branch() -> None:
    """Create the develop branch if it doesn't already exist."""
    if _branch_exists("develop"):
        logger.debug("Branch 'develop' already exists")
        click.echo("Branch 'develop' is ready.")
    else:
        _create_branch("develop")
        logger.debug("Created branch 'develop'")
        click.echo("Created branch 'develop'.")
