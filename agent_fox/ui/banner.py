"""CLI banner rendering with version display.

Renders a themed banner with the project name and version when
the CLI is invoked without a subcommand.

Requirements: 01-REQ-1.3
"""

from __future__ import annotations

from agent_fox import __version__
from agent_fox.ui.theme import AppTheme


def render_banner(theme: AppTheme) -> None:
    """Render the CLI banner with project name and version.

    Args:
        theme: The app theme to use for styled output.
    """
    theme.header(f"agent-fox v{__version__}")
    theme.print(theme.playful("starting"), role="info")
