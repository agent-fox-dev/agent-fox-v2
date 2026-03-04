"""CLI ingest command: ingest ADRs and git commits into the knowledge store.

Requirements: 12-REQ-4.1, 12-REQ-4.2, 12-REQ-4.3
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from agent_fox.knowledge.db import open_knowledge_store
from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.ingest import KnowledgeIngestor


@click.command("ingest")
@click.option(
    "--adrs/--no-adrs",
    default=True,
    help="Ingest ADRs from docs/adr/ (default: on).",
)
@click.option(
    "--git-commits/--no-git-commits",
    default=True,
    help="Ingest git commit messages (default: on).",
)
@click.option(
    "--limit",
    type=int,
    default=100,
    help="Max git commits to ingest (default: 100).",
)
@click.option(
    "--since",
    type=str,
    default=None,
    help="Only ingest git commits after this date (ISO 8601).",
)
@click.pass_context
def ingest_cmd(
    ctx: click.Context,
    adrs: bool,
    git_commits: bool,
    limit: int,
    since: str | None,
) -> None:
    """Ingest ADRs and git commits into the knowledge store.

    Parses additional knowledge sources and stores them as facts
    with embeddings for semantic search via `agent-fox ask`.

    Example:
        agent-fox ingest
        agent-fox ingest --no-adrs --since 2026-01-01
    """
    config = ctx.obj["config"].knowledge

    db = open_knowledge_store(config)
    if db is None:
        click.echo("Error: Knowledge store is unavailable.", err=True)
        sys.exit(1)

    try:
        embedder = EmbeddingGenerator(config)
        ingestor = KnowledgeIngestor(
            db.connection,
            embedder,
            project_root=Path.cwd(),
        )

        if adrs:
            result = ingestor.ingest_adrs()
            click.echo(
                f"ADRs: {result.facts_added} added, "
                f"{result.facts_skipped} skipped"
                + (
                    f", {result.embedding_failures} embedding failures"
                    if result.embedding_failures
                    else ""
                )
            )

        if git_commits:
            result = ingestor.ingest_git_commits(limit=limit, since=since)
            click.echo(
                f"Git commits: {result.facts_added} added, "
                f"{result.facts_skipped} skipped"
                + (
                    f", {result.embedding_failures} embedding failures"
                    if result.embedding_failures
                    else ""
                )
            )

    finally:
        db.close()
