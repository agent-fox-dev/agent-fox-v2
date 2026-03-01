"""Terminal theme system with Rich styles.

Provides themed console output with configurable color roles and
playful/neutral message variants. Invalid Rich style strings fall
back to the corresponding default color for that role.

Requirements: 01-REQ-7.1, 01-REQ-7.2, 01-REQ-7.3, 01-REQ-7.4, 01-REQ-7.E1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rich.console import Console
from rich.style import Style
from rich.theme import Theme

from agent_fox.core.config import ThemeConfig

logger = logging.getLogger(__name__)

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

        rich_theme = Theme(
            {role: style for role, style in styles.items() if style}
        )
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
