"""CLI command for pattern detection: agent-fox patterns.

Detects and displays recurring cause-effect patterns from session
history and the causal graph.

Requirements: 13-REQ-5.3, 13-REQ-5.E1
"""

from __future__ import annotations

import logging

import click

from agent_fox.knowledge.db import open_knowledge_store
from agent_fox.knowledge.patterns import detect_patterns, render_patterns

logger = logging.getLogger(__name__)


@click.command("patterns")
@click.option(
    "--min-occurrences",
    default=2,
    type=int,
    help="Minimum co-occurrences to report a pattern.",
)
@click.pass_context
def patterns_cmd(ctx: click.Context, min_occurrences: int) -> None:
    """Detect and display recurring cause-effect patterns.

    Analyzes session history and the causal graph to find recurring
    sequences (e.g., "module X changes -> test Y breaks").
    """
    config = ctx.obj["config"]

    db = open_knowledge_store(config.knowledge)
    if db is None:
        click.echo("No recurring patterns detected. More session history is needed.")
        return

    try:
        patterns = detect_patterns(
            db.connection,
            min_occurrences=min_occurrences,
        )
    finally:
        db.close()

    # REQ-5.E1: If no patterns detected, display informational message
    use_color = ctx.color is not False
    output = render_patterns(patterns, use_color=use_color)
    click.echo(output)
