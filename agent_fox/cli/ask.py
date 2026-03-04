"""CLI ask command for querying the Fox Ball knowledge oracle.

Wires up the oracle pipeline and renders the answer with sources,
contradictions, and confidence indicator.  Supports ``--timeline``
for temporal causal queries (13-REQ-4.1, 13-REQ-4.2).

Requirements: 12-REQ-5.1, 12-REQ-5.E1, 12-REQ-5.E2, 12-REQ-2.E2,
              13-REQ-4.1, 13-REQ-4.2, 13-REQ-6.1
"""

from __future__ import annotations

import sys

import click

from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.knowledge.db import open_knowledge_store
from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.oracle import Oracle
from agent_fox.knowledge.search import VectorSearch
from agent_fox.knowledge.temporal import temporal_query


@click.command("ask")
@click.argument("question")
@click.option(
    "--top-k",
    type=int,
    default=None,
    help="Number of facts to retrieve (default: from config)",
)
@click.option(
    "--timeline",
    is_flag=True,
    default=False,
    help="Return a causal timeline instead of a synthesized answer.",
)
@click.pass_context
def ask_command(
    ctx: click.Context,
    question: str,
    top_k: int | None,
    timeline: bool,
) -> None:
    """Ask a question about your project's accumulated knowledge.

    Embeds the question, retrieves relevant facts from the knowledge
    store, and synthesizes a grounded answer with source citations.

    Use --timeline to get a causal timeline showing cause-effect chains
    instead of a synthesized answer.

    Examples:
        agent-fox ask "why did we choose DuckDB over SQLite?"
        agent-fox ask --timeline "what happened with the auth module?"
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

        if timeline:
            _run_timeline_query(db.connection, embedder, question, config.ask_top_k)
        else:
            _run_oracle_query(embedder, search, config, question)

    except KnowledgeStoreError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        db.close()


def _run_oracle_query(embedder, search, config, question: str) -> None:
    """Standard RAG oracle pipeline (12-REQ-5.1)."""
    oracle = Oracle(embedder, search, config)
    answer = oracle.ask(question)

    click.echo(f"\n{answer.answer}\n")
    click.echo(f"Confidence: {answer.confidence}")

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

    if answer.contradictions:
        click.echo("\nContradictions detected:")
        for contradiction in answer.contradictions:
            click.echo(f"  ! {contradiction}")


def _run_timeline_query(conn, embedder, question: str, top_k: int) -> None:
    """Temporal causal timeline query (13-REQ-4.1, 13-REQ-4.2)."""
    query_embedding = embedder.embed_text(question)
    tl = temporal_query(conn, question, query_embedding, top_k=top_k)

    use_color = sys.stdout.isatty()
    click.echo(tl.render(use_color=use_color))
