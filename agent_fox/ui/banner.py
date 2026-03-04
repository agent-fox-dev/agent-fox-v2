"""CLI banner rendering with fox art, version, model, and cwd.

Renders a themed banner with the fox ASCII art mascot, resolved
coding model, and current working directory on every CLI invocation.

Requirements: 01-REQ-1.3, 14-REQ-1.1, 14-REQ-1.2, 14-REQ-2.1,
              14-REQ-2.2, 14-REQ-2.3, 14-REQ-2.E1, 14-REQ-3.1,
              14-REQ-3.2, 14-REQ-3.E1
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_fox import __version__
from agent_fox.core.config import ModelConfig
from agent_fox.core.models import resolve_model
from agent_fox.ui.theme import AppTheme

FOX_ART = r"""   /\_/\  _
  / o.o \/ \
 ( > ^ < )  )
  \_^/\_/--'"""


def _get_git_revision() -> str | None:
    """Return the short git revision hash, or None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
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
