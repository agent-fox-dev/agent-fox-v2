"""Terminal theme and banner rendering.

Provides themed console output with configurable color roles and
playful/neutral message variants, plus the CLI banner with fox ASCII
art, version, model, and current working directory.

Requirements: 01-REQ-7.1, 01-REQ-7.2, 01-REQ-7.3, 01-REQ-7.4, 01-REQ-7.E1,
              01-REQ-1.3, 14-REQ-1.1, 14-REQ-1.2, 14-REQ-2.1,
              14-REQ-2.2, 14-REQ-2.3, 14-REQ-2.E1, 14-REQ-3.1,
              14-REQ-3.2, 14-REQ-3.E1
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.style import Style
from rich.theme import Theme

from agent_fox import __version__
from agent_fox._build_info import GIT_REVISION
from agent_fox.core.config import ModelConfig, ThemeConfig
from agent_fox.core.models import resolve_model

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

# Default style values matching ThemeConfig defaults
_DEFAULT_STYLES: dict[str, str] = {
    "header": "bold #ff8c00",
    "success": "bold green",
    "error": "bold red",
    "warning": "bold yellow",
    "info": "#daa520",
    "tool": "bold #cd853f",
    "muted": "dim",
}

# Playful (fox-themed) messages keyed by event
_PLAYFUL_MESSAGES: dict[str, str] = {
    "task_complete": "Tail wagging — task complete!",
    "thinking": "The fox is thinking...",
    "starting": "The fox is on the hunt!",
    "error": "The fox stumbled!",
    "success": "The fox nailed it!",
    "init": "The fox is setting up its den!",
    "waiting": "The fox is watching patiently...",
}

# Neutral (professional) messages keyed by event
_NEUTRAL_MESSAGES: dict[str, str] = {
    "task_complete": "Task complete.",
    "thinking": "Processing...",
    "starting": "Starting task.",
    "error": "An error occurred.",
    "success": "Operation succeeded.",
    "init": "Initializing project.",
    "waiting": "Waiting...",
}


def _validate_style(style_str: str, role: str) -> str:
    """Validate a Rich style string, falling back to default if invalid.

    Args:
        style_str: The style string to validate.
        role: The color role name (for logging and default lookup).

    Returns:
        The original style string if valid, or the default for that role.
    """
    try:
        Style.parse(style_str)
        return style_str
    except Exception:
        default = _DEFAULT_STYLES.get(role, "")
        logger.warning(
            "Invalid theme style for '%s': '%s', using default '%s'",
            role,
            style_str,
            default,
        )
        return default


@dataclass
class AppTheme:
    """Themed console output with configurable color roles."""

    config: ThemeConfig
    console: Console = field(init=False)

    def __post_init__(self) -> None:
        """Initialize the Rich console with validated theme styles."""
        # Validate each style from config, falling back to defaults
        roles = ("header", "success", "error", "warning", "info", "tool", "muted")
        styles: dict[str, str] = {}
        for role in roles:
            raw_style = getattr(self.config, role)
            styles[role] = _validate_style(raw_style, role)

        rich_theme = Theme({role: style for role, style in styles.items() if style})
        self.console = Console(theme=rich_theme)

    def styled(self, text: str, role: str) -> str:
        """Return text styled for the given role.

        Uses Rich markup to apply the style. Returns plain text if the
        role is unknown.
        """
        return f"[{role}]{text}[/{role}]"

    def print(self, text: str, role: str = "info") -> None:
        """Print styled text to console."""
        self.console.print(f"[{role}]{text}[/{role}]")

    def success(self, text: str) -> None:
        """Print a success message."""
        self.print(text, role="success")

    def error(self, text: str) -> None:
        """Print an error message."""
        self.print(text, role="error")

    def warning(self, text: str) -> None:
        """Print a warning message."""
        self.print(text, role="warning")

    def header(self, text: str) -> None:
        """Print a header message."""
        self.print(text, role="header")

    def playful(self, key: str) -> str:
        """Return playful or neutral message based on config.

        Args:
            key: The message key (e.g., "task_complete", "thinking").

        Returns:
            A fox-themed message if playful mode is enabled,
            otherwise a neutral professional message.
        """
        if self.config.playful:
            return _PLAYFUL_MESSAGES.get(key, key)
        return _NEUTRAL_MESSAGES.get(key, key)


def create_theme(config: ThemeConfig) -> AppTheme:
    """Create an AppTheme from configuration.

    Args:
        config: Theme configuration with color roles and playful flag.

    Returns:
        A fully initialized AppTheme ready for styled output.
    """
    return AppTheme(config=config)


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

FOX_ART = r"""
   /\_/\   _
  / o.o \/\ \
 ( > ^ < ) ) )
  \_^/\_/--'"""


def _get_git_revision() -> str | None:
    """Return the short git revision of the *agent-fox* package.

    Resolution order:
    1. Build-time stamp in ``_build_info.GIT_REVISION`` (set by
       ``make stamp-version`` before a non-editable install).
    2. Live ``git rev-parse`` executed inside the package source tree
       (works for editable / dev installs where the source *is* a git
       checkout).

    The previous implementation ran ``git rev-parse`` in the CWD,
    which returned the revision of whatever repo the user was working
    in — not agent-fox's own revision.
    """
    if GIT_REVISION is not None:
        return GIT_REVISION

    # Editable-install fallback: resolve from the package source dir.
    package_dir = str(Path(__file__).resolve().parent.parent)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=package_dir,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _resolve_coding_model_display(model_config: ModelConfig) -> str:
    """Resolve the coding model to a display string.

    Returns the model ID (e.g., 'claude-opus-4-6') on success,
    or the raw config value (e.g., 'ADVANCED') on failure.
    """
    try:
        entry = resolve_model(model_config.coding)
        return entry.model_id
    except Exception:
        return model_config.coding


def render_banner(
    theme: AppTheme,
    model_config: ModelConfig,
    quiet: bool = False,
) -> None:
    """Render the CLI banner with fox art, version, model, and cwd.

    Args:
        theme: The app theme for styled output.
        model_config: The model configuration to resolve the coding model.
        quiet: If True, suppress all banner output.
    """
    if quiet:
        return

    console = theme.console

    # 14-REQ-1.1, 14-REQ-1.2: Fox art styled with header role
    # Print directly via console.print(style=...) to avoid Rich markup
    # parsing of backslashes in the ASCII art.
    for line in FOX_ART.splitlines():
        console.print(line, style="header", highlight=False)

    # 14-REQ-2.1, 14-REQ-2.2, 14-REQ-2.3, 14-REQ-2.E1: Version + model line
    model_display = _resolve_coding_model_display(model_config)
    revision = _get_git_revision()
    version_part = f"agent-fox v{__version__}"
    if revision:
        version_part += f" ({revision})."
    version_line = f"{version_part}  model: {model_display}"
    console.print(version_line, style="header", highlight=False)

    # 14-REQ-3.1, 14-REQ-3.2, 14-REQ-3.E1: Working directory with fallback
    try:
        cwd = str(Path.cwd())
    except OSError:
        cwd = "(unknown)"
    console.print(cwd, style="muted", highlight=False)
