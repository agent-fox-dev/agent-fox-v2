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
    json_mode = ctx.obj.get("json", False)
    original, surviving = compact()
    removed = original - surviving

    # 23-REQ-3.6: JSON output for compact command
    if json_mode:
        from agent_fox.cli.json_io import emit

        emit({
            "original": original,
            "surviving": surviving,
            "removed": removed,
        })
        return

    if original == 0:
        click.echo("Knowledge base is empty — nothing to compact.")
        return

    click.echo(f"Compacted: {original} → {surviving} facts ({removed} removed).")
