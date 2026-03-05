"""CLI ask command for querying the Fox Ball knowledge oracle.

Wires up the oracle pipeline and renders the answer with sources,
contradictions, and confidence indicator.  Supports ``--timeline``
for temporal causal queries (13-REQ-4.1, 13-REQ-4.2).

Requirements: 12-REQ-5.1, 12-REQ-5.E1, 12-REQ-5.E2, 12-REQ-2.E2,
              13-REQ-4.1, 13-REQ-4.2, 13-REQ-6.1,
              23-REQ-5.2, 23-REQ-7.2
"""

from __future__ import annotations

import sys

import click

from agent_fox.cli import json_io
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
    json_mode: bool = ctx.obj.get("json", False)

    # 23-REQ-7.1, 23-REQ-7.2: read stdin JSON when in JSON mode
    if json_mode:
        stdin_data = json_io.read_stdin()
        # CLI flags take precedence over stdin values
        if not question and "question" in stdin_data:
            question = stdin_data["question"]
        if top_k is None and "top_k" in stdin_data:
            top_k = int(stdin_data["top_k"])

    # Override top_k if provided via CLI
    if top_k is not None:
        config = config.model_copy(update={"ask_top_k": top_k})

    # Open the knowledge store (graceful degradation)
    db = open_knowledge_store(config)
    if db is None:
        if json_mode:
            json_io.emit_error("Knowledge store is unavailable.")
            sys.exit(1)
        click.echo("Error: Knowledge store is unavailable.", err=True)
        sys.exit(1)

    try:
        # Create the pipeline components
        embedder = EmbeddingGenerator(config)
        search = VectorSearch(db.connection, config)

        # Check whether the store has any embedded facts
        if not search.has_embeddings():
            if json_mode:
                json_io.emit({
                    "answer": None,
                    "sources": [],
                    "message": "No knowledge accumulated yet.",
                })
                return
            click.echo(
                "No knowledge has been accumulated yet. "
                "Run some coding sessions first to build up the knowledge base."
            )
            return

        if timeline:
            if json_mode:
                _run_timeline_query_json(
                    db.connection, embedder, question, config.ask_top_k,
                )
            else:
                _run_timeline_query(db.connection, embedder, question, config.ask_top_k)
        else:
            if json_mode:
                _run_oracle_query_json(embedder, search, config, question)
            else:
                _run_oracle_query(embedder, search, config, question)

    except KnowledgeStoreError as exc:
        if json_mode:
            json_io.emit_error(str(exc))
            sys.exit(1)
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


def _run_oracle_query_json(embedder, search, config, question: str) -> None:
    """Oracle query with JSON output (23-REQ-5.2)."""
    oracle = Oracle(embedder, search, config)
    answer = oracle.ask(question)

    sources = []
    for src in answer.sources:
        sources.append({
            "fact_id": src.fact_id,
            "content": src.content,
            "spec_name": src.spec_name,
            "session_id": src.session_id,
            "commit_sha": src.commit_sha,
            "similarity": src.similarity,
        })

    json_io.emit({
        "answer": answer.answer,
        "confidence": answer.confidence,
        "sources": sources,
        "contradictions": answer.contradictions or [],
    })


def _run_timeline_query(conn, embedder, question: str, top_k: int) -> None:
    """Temporal causal timeline query (13-REQ-4.1, 13-REQ-4.2)."""
    query_embedding = embedder.embed_text(question)
    tl = temporal_query(conn, question, query_embedding, top_k=top_k)

    use_color = sys.stdout.isatty()
    click.echo(tl.render(use_color=use_color))


def _run_timeline_query_json(conn, embedder, question: str, top_k: int) -> None:
    """Temporal causal timeline query with JSON output (23-REQ-5.2)."""
    query_embedding = embedder.embed_text(question)
    tl = temporal_query(conn, question, query_embedding, top_k=top_k)

    nodes = []
    for node in tl.nodes:
        nodes.append({
            "fact_id": node.fact_id,
            "content": node.content,
            "spec_name": node.spec_name,
            "session_id": node.session_id,
            "commit_sha": node.commit_sha,
            "timestamp": node.timestamp,
            "relationship": node.relationship,
            "depth": node.depth,
        })

    json_io.emit({
        "query": tl.query,
        "timeline": nodes,
    })
