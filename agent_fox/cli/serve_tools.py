"""CLI command for launching the fox tools MCP server.

Requirements: 29-REQ-7.3
"""

from __future__ import annotations

import click


@click.command("serve-tools")
@click.option(
    "--allowed-dirs",
    multiple=True,
    help="Restrict file operations to these directories.",
)
def serve_tools_cmd(allowed_dirs: tuple[str, ...]) -> None:
    """Launch the fox tools MCP server on stdio."""
    from agent_fox.tools.server import run_server

    dirs = list(allowed_dirs) if allowed_dirs else None
    run_server(allowed_dirs=dirs)
