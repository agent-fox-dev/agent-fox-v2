"""CLI ask command for querying the Fox Ball knowledge oracle.

Wires up the oracle pipeline and renders the answer with sources,
contradictions, and confidence indicator.

Requirements: 12-REQ-5.1, 12-REQ-5.E1, 12-REQ-5.E2, 12-REQ-2.E2
"""

from __future__ import annotations

import sys

import click

from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.knowledge.db import open_knowledge_store
from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.oracle import Oracle
from agent_fox.knowledge.search import VectorSearch


@click.command("ask")
@click.argument("question")
@click.option(
    "--top-k",
    type=int,
    default=None,
    help="Number of facts to retrieve (default: from config)",
)
@click.pass_context
def ask_command(ctx: click.Context, question: str, top_k: int | None) -> None:
    """Ask a question about your project's accumulated knowledge.

    Embeds the question, retrieves relevant facts from the knowledge
    store, and synthesizes a grounded answer with source citations.

    Example:
        agent-fox ask "why did we choose DuckDB over SQLite?"
    """
    config = ctx.obj["config"].knowledge

    # Override top_k if provided via CLI
    if top_k is not None:
        config = config.model_copy(update={"ask_top_k": top_k})

    # Open the knowledge store (graceful degradation)
    db = open_knowledge_store(config)
    if db is None:
        click.echo("Error: Knowledge store is unavailable.", err=True)
        sys.exit(1)

    try:
        # Create the pipeline components
        embedder = EmbeddingGenerator(config)
        search = VectorSearch(db.connection, config)

        # Check whether the store has any embedded facts
        if not search.has_embeddings():
            click.echo(
                "No knowledge has been accumulated yet. "
                "Run some coding sessions first to build up the knowledge base."
            )
            return

        # Run the oracle RAG pipeline
        oracle = Oracle(embedder, search, config)
        answer = oracle.ask(question)

        # Render the answer
        click.echo(f"\n{answer.answer}\n")

        # Render confidence
        click.echo(f"Confidence: {answer.confidence}")

        # Render sources
        if answer.sources:
            click.echo("\nSources:")
            for source in answer.sources:
                provenance_parts: list[str] = []
                if source.spec_name:
                    provenance_parts.append(f"spec: {source.spec_name}")
                if source.session_id:
                    provenance_parts.append(f"session: {source.session_id}")
                if source.commit_sha:
                    provenance_parts.append(f"commit: {source.commit_sha}")
                provenance = ", ".join(provenance_parts) if provenance_parts else ""
                click.echo(
                    f"  - [{source.fact_id[:8]}] {source.content[:80]} "
                    f"({provenance}, similarity: {source.similarity:.2f})"
                )

        # Render contradictions if present
        if answer.contradictions:
            click.echo("\nContradictions detected:")
            for contradiction in answer.contradictions:
                click.echo(f"  ! {contradiction}")

    except KnowledgeStoreError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        db.close()
