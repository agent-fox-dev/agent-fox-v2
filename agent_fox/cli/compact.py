"""CLI compact command: deduplicate and clean up the memory store.

Requirements: 05-REQ-5.1, 05-REQ-5.2, 05-REQ-5.3
"""

from __future__ import annotations

import click

from agent_fox.memory.compaction import compact


@click.command("compact")
@click.pass_context
def compact_cmd(ctx: click.Context) -> None:
    """Compact the knowledge base by removing duplicates and superseded facts.

    Deduplicates by content hash and resolves supersession chains,
    then rewrites the JSONL file with surviving facts.

    Example:
        agent-fox compact
    """
    original, surviving = compact()

    if original == 0:
        click.echo("Knowledge base is empty — nothing to compact.")
        return

    removed = original - surviving
    click.echo(f"Compacted: {original} → {surviving} facts ({removed} removed).")
