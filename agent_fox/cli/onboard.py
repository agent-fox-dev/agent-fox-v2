"""CLI command for knowledge store onboarding.

Provides the ``onboard`` command that populates the knowledge store for
existing codebases by running a six-phase pipeline: entity graph analysis,
bootstrap ingestion (ADRs/errata/git commits), git pattern mining, LLM
code analysis, LLM documentation mining, and embedding generation.

Requirements: 101-REQ-1.1, 101-REQ-1.2, 101-REQ-1.3, 101-REQ-1.4,
              101-REQ-1.5, 101-REQ-1.6, 101-REQ-1.E1
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from pathlib import Path

import click

from agent_fox.core.config import load_config
from agent_fox.knowledge.db import open_knowledge_store
from agent_fox.knowledge.onboard import OnboardResult, run_onboard

logger = logging.getLogger(__name__)


def _print_summary(result: OnboardResult) -> None:
    """Print a human-readable onboarding summary to stderr.

    Requirement: 101-REQ-1.4
    """
    click.echo("Onboarding complete.", err=True)
    click.echo(f"  Elapsed: {result.elapsed_seconds:.1f}s", err=True)
    click.echo(
        f"  Entity graph: {result.entities_upserted} entities, "
        f"{result.edges_upserted} edges",
        err=True,
    )
    click.echo(
        f"  Ingestion: {result.adrs_ingested} ADRs, "
        f"{result.errata_ingested} errata, "
        f"{result.git_commits_ingested} git commits",
        err=True,
    )
    click.echo(
        f"  Git mining: {result.fragile_areas_created} fragile areas, "
        f"{result.cochange_patterns_created} co-change patterns",
        err=True,
    )
    click.echo(
        f"  Code analysis: {result.code_facts_created} facts from "
        f"{result.code_files_analyzed} files",
        err=True,
    )
    click.echo(
        f"  Doc mining: {result.doc_facts_created} facts from "
        f"{result.docs_analyzed} docs",
        err=True,
    )
    click.echo(
        f"  Embeddings: {result.embeddings_generated} generated, "
        f"{result.embeddings_failed} failed",
        err=True,
    )
    if result.phases_skipped:
        click.echo(
            f"  Skipped phases: {', '.join(result.phases_skipped)}", err=True
        )
    if result.phases_errored:
        click.echo(
            f"  Errored phases: {', '.join(result.phases_errored)}", err=True
        )


@click.command("onboard")
@click.option(
    "--path",
    "project_root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Project root directory (default: current working directory)",
)
@click.option(
    "--skip-entities",
    is_flag=True,
    default=False,
    help="Skip entity graph analysis phase",
)
@click.option(
    "--skip-ingestion",
    is_flag=True,
    default=False,
    help="Skip ADR/errata/git commit ingestion phase",
)
@click.option(
    "--skip-mining",
    is_flag=True,
    default=False,
    help="Skip git pattern mining phase",
)
@click.option(
    "--skip-code-analysis",
    is_flag=True,
    default=False,
    help="Skip LLM code analysis phase",
)
@click.option(
    "--skip-doc-mining",
    is_flag=True,
    default=False,
    help="Skip LLM documentation mining phase",
)
@click.option(
    "--skip-embeddings",
    is_flag=True,
    default=False,
    help="Skip embedding generation phase",
)
@click.option(
    "--model",
    type=str,
    default="STANDARD",
    show_default=True,
    help="Model tier for LLM phases",
)
@click.option(
    "--mining-days",
    type=int,
    default=365,
    show_default=True,
    help="Days of git history to analyze",
)
@click.option(
    "--fragile-threshold",
    type=int,
    default=20,
    show_default=True,
    help="Min commits to flag a file as a fragile area",
)
@click.option(
    "--cochange-threshold",
    type=int,
    default=5,
    show_default=True,
    help="Min co-occurrences for a co-change pattern",
)
@click.option(
    "--max-files",
    type=int,
    default=0,
    show_default=True,
    help="Max source files for code analysis (0 = all)",
)
@click.pass_context
def onboard_cmd(
    ctx: click.Context,
    project_root: Path | None,
    skip_entities: bool,
    skip_ingestion: bool,
    skip_mining: bool,
    skip_code_analysis: bool,
    skip_doc_mining: bool,
    skip_embeddings: bool,
    model: str,
    mining_days: int,
    fragile_threshold: int,
    cochange_threshold: int,
    max_files: int,
) -> None:
    """Onboard an existing codebase into the agent-fox knowledge store.

    Runs a six-phase pipeline to populate the knowledge store:
    entity graph analysis, bootstrap ingestion (ADRs/errata/git commits),
    git pattern mining, LLM code analysis, LLM documentation mining,
    and embedding generation.
    """
    json_mode = ctx.obj.get("json", False) if ctx.obj else False

    # Resolve project root.
    # Requirements: 101-REQ-1.2, 101-REQ-1.3
    if project_root is None:
        project_root = Path.cwd()

    # Load configuration from the project's config file (or defaults).
    config_path = project_root / ".agent-fox" / "config.toml"
    config = load_config(config_path)

    # Open knowledge store and run the pipeline.
    with open_knowledge_store(config.knowledge) as db:
        result = asyncio.run(
            run_onboard(
                project_root,
                config,
                db,
                skip_entities=skip_entities,
                skip_ingestion=skip_ingestion,
                skip_mining=skip_mining,
                skip_code_analysis=skip_code_analysis,
                skip_doc_mining=skip_doc_mining,
                skip_embeddings=skip_embeddings,
                model=model,
                mining_days=mining_days,
                fragile_threshold=fragile_threshold,
                cochange_threshold=cochange_threshold,
                max_files=max_files,
            )
        )

    # Output results.
    # Requirements: 101-REQ-1.4, 101-REQ-1.5
    if json_mode:
        from agent_fox.cli.json_io import emit

        emit(dataclasses.asdict(result))
    else:
        _print_summary(result)
