"""Onboarding orchestrator for knowledge store population.

Composes entity graph analysis, bootstrap ingestion, git pattern mining,
LLM code analysis, LLM documentation mining, and embedding generation
into a single pipeline that seeds the knowledge store for existing
codebases.

Requirements: 101-REQ-1.6, 101-REQ-2.1, 101-REQ-2.2, 101-REQ-2.E1,
              101-REQ-3.1, 101-REQ-3.2, 101-REQ-3.3, 101-REQ-3.E1,
              101-REQ-4.7, 101-REQ-5.4, 101-REQ-6.3, 101-REQ-7.1,
              101-REQ-7.2, 101-REQ-7.E1, 101-REQ-8.1, 101-REQ-8.2,
              101-REQ-8.3, 101-REQ-1.E2
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from agent_fox.core.config import AgentFoxConfig
from agent_fox.knowledge.code_analysis import analyze_code_with_llm
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.doc_mining import mine_docs_with_llm
from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.git_mining import mine_git_patterns
from agent_fox.knowledge.ingest import KnowledgeIngestor
from agent_fox.knowledge.static_analysis import analyze_codebase

logger = logging.getLogger("agent_fox.knowledge.onboard")


@dataclass
class OnboardResult:
    """Aggregated result of all onboarding phases.

    Requirements: 101-REQ-8.1, 101-REQ-8.3
    """

    # Entity graph phase
    entities_upserted: int = 0
    edges_upserted: int = 0
    entities_soft_deleted: int = 0
    # Bootstrap ingestion phase
    adrs_ingested: int = 0
    errata_ingested: int = 0
    git_commits_ingested: int = 0
    # Git mining phase
    fragile_areas_created: int = 0
    cochange_patterns_created: int = 0
    commits_analyzed: int = 0
    files_analyzed: int = 0
    # LLM code analysis phase
    code_facts_created: int = 0
    code_files_analyzed: int = 0
    code_files_skipped: int = 0
    # Documentation mining phase
    doc_facts_created: int = 0
    docs_analyzed: int = 0
    docs_skipped: int = 0
    # Embedding phase
    embeddings_generated: int = 0
    embeddings_failed: int = 0
    # Meta
    phases_skipped: list[str] = field(default_factory=list)
    phases_errored: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


def _is_git_repo(path: Path) -> bool:
    """Check if the given directory is a git repository.

    Checks for a ``.git`` directory directly inside *path*.

    Args:
        path: Directory to check.

    Returns:
        True if path contains a .git directory, False otherwise.

    Requirement: 101-REQ-1.E2
    """
    return (path / ".git").is_dir()


def _generate_missing_embeddings(
    conn: duckdb.DuckDBPyConnection,
    embedder: EmbeddingGenerator,
) -> tuple[int, int]:
    """Generate embeddings for all facts without embeddings.

    Queries ``memory_facts`` for facts that have no corresponding entry in
    ``memory_embeddings``, then generates and stores embeddings for each.
    Failures are handled best-effort: logged as warnings and counted.

    Args:
        conn: DuckDB connection with knowledge schema.
        embedder: EmbeddingGenerator instance.

    Returns:
        Tuple of (generated, failed) counts.

    Requirements: 101-REQ-7.1, 101-REQ-7.E1
    """
    rows = conn.execute(
        "SELECT CAST(mf.id AS VARCHAR), mf.content "
        "FROM memory_facts mf "
        "LEFT JOIN memory_embeddings me ON me.id = mf.id "
        "WHERE me.id IS NULL AND mf.superseded_by IS NULL"
    ).fetchall()

    generated = 0
    failed = 0
    dim = embedder.embedding_dimensions

    for fact_id, content in rows:
        try:
            embedding = embedder.embed_text(content)
            if embedding is not None:
                conn.execute(
                    f"INSERT OR IGNORE INTO memory_embeddings (id, embedding) "
                    f"VALUES (?::UUID, ?::FLOAT[{dim}])",
                    [fact_id, embedding],
                )
                generated += 1
            else:
                logger.warning("Embedding returned None for fact %s", fact_id)
                failed += 1
        except Exception:
            logger.warning(
                "Embedding failed for fact %s", fact_id, exc_info=True
            )
            failed += 1

    return generated, failed


async def run_onboard(
    project_root: Path,
    config: AgentFoxConfig,
    db: KnowledgeDB,
    *,
    skip_entities: bool = False,
    skip_ingestion: bool = False,
    skip_mining: bool = False,
    skip_code_analysis: bool = False,
    skip_doc_mining: bool = False,
    skip_embeddings: bool = False,
    model: str = "STANDARD",
    mining_days: int = 365,
    fragile_threshold: int = 20,
    cochange_threshold: int = 5,
    max_files: int = 0,
) -> OnboardResult:
    """Run the onboarding pipeline and return aggregated results.

    Phases run sequentially:

    1. Entity graph analysis (structural foundation)
    2. Bootstrap ingestion (ADRs, errata, git commits)
    3. Git pattern mining (deterministic)
    4. LLM code analysis (reads source, extracts architectural facts)
    5. LLM documentation mining (reads docs, extracts conventions)
    6. Embedding generation (embeds all unembedded facts)

    Each phase is independently error-handled: a failure records the phase
    name in ``phases_errored`` but does not abort subsequent phases.
    Skip flags record the phase name in ``phases_skipped``.

    Args:
        project_root: Root directory of the project to onboard.
        config: Loaded agent-fox configuration.
        db: Open KnowledgeDB instance.
        skip_entities: Skip entity graph analysis phase.
        skip_ingestion: Skip ADR/errata/git commit ingestion phase.
        skip_mining: Skip git pattern mining phase.
        skip_code_analysis: Skip LLM code analysis phase.
        skip_doc_mining: Skip LLM documentation mining phase.
        skip_embeddings: Skip embedding generation phase.
        model: Model tier for LLM phases (default: ``"STANDARD"``).
        mining_days: Days of git history to analyze (default: 365).
        fragile_threshold: Min commits to flag as fragile (default: 20).
        cochange_threshold: Min co-occurrences for a pattern (default: 5).
        max_files: Max source files for code analysis (0 = all).

    Returns:
        OnboardResult with per-phase counts and timing.

    Requirements: 101-REQ-1.6, 101-REQ-2.1, 101-REQ-2.2, 101-REQ-2.E1,
                  101-REQ-3.1, 101-REQ-3.2, 101-REQ-3.3, 101-REQ-3.E1,
                  101-REQ-4.7, 101-REQ-5.4, 101-REQ-6.3, 101-REQ-7.1,
                  101-REQ-7.2, 101-REQ-7.E1, 101-REQ-8.1, 101-REQ-8.2,
                  101-REQ-8.3, 101-REQ-1.E2
    """
    start_time = time.monotonic()
    result = OnboardResult()
    conn = db.connection
    is_git = _is_git_repo(project_root)

    if not is_git:
        logger.warning(
            "Project root %s is not a git repository; "
            "git-dependent phases will be skipped",
            project_root,
        )

    # -------------------------------------------------------------------------
    # Phase 1: Entity Graph Analysis
    # Requirements: 101-REQ-2.1, 101-REQ-2.2, 101-REQ-2.E1
    # -------------------------------------------------------------------------
    if skip_entities:
        result.phases_skipped.append("entities")
        logger.info("Skipping entity graph phase (--skip-entities)")
    else:
        logger.info("Phase 1: entity graph analysis")
        try:
            analysis = analyze_codebase(project_root, conn)
            result.entities_upserted = analysis.entities_upserted
            result.edges_upserted = analysis.edges_upserted
            result.entities_soft_deleted = analysis.entities_soft_deleted
            logger.info(
                "Entity graph phase complete: %d entities, %d edges",
                result.entities_upserted,
                result.edges_upserted,
            )
        except Exception:
            logger.error("Entity graph phase failed", exc_info=True)
            result.phases_errored.append("entities")

    # -------------------------------------------------------------------------
    # Phase 2: Bootstrap Ingestion
    # Requirements: 101-REQ-3.1, 101-REQ-3.2, 101-REQ-3.3, 101-REQ-3.E1
    # -------------------------------------------------------------------------
    if skip_ingestion:
        result.phases_skipped.append("ingestion")
        logger.info("Skipping ingestion phase (--skip-ingestion)")
    else:
        logger.info("Phase 2: bootstrap ingestion")
        embedder = EmbeddingGenerator(config.knowledge)
        ingestor = KnowledgeIngestor(conn, embedder, project_root)

        # ADR ingestion — best-effort per source (101-REQ-3.E1)
        try:
            adr_result = ingestor.ingest_adrs()
            result.adrs_ingested = adr_result.facts_added
            logger.info("ADR ingestion: %d facts added", result.adrs_ingested)
        except Exception:
            logger.warning("ADR ingestion failed", exc_info=True)

        # Errata ingestion — best-effort per source (101-REQ-3.E1)
        try:
            errata_result = ingestor.ingest_errata()
            result.errata_ingested = errata_result.facts_added
            logger.info(
                "Errata ingestion: %d facts added", result.errata_ingested
            )
        except Exception:
            logger.warning("Errata ingestion failed", exc_info=True)

        # Git commit ingestion — only for git repos (101-REQ-3.3)
        if is_git:
            try:
                git_result = ingestor.ingest_git_commits(limit=10000)
                result.git_commits_ingested = git_result.facts_added
                logger.info(
                    "Git commit ingestion: %d facts added",
                    result.git_commits_ingested,
                )
            except Exception:
                logger.warning("Git commit ingestion failed", exc_info=True)
        else:
            logger.info(
                "Skipping git commit ingestion (not a git repository)"
            )

    # -------------------------------------------------------------------------
    # Phase 3: Git Pattern Mining
    # Requirements: 101-REQ-4.7, 101-REQ-4.E1
    # -------------------------------------------------------------------------
    if skip_mining:
        result.phases_skipped.append("mining")
        logger.info("Skipping git pattern mining phase (--skip-mining)")
    elif not is_git:
        # 101-REQ-4.E1: skip mining for non-git repositories
        logger.warning(
            "Skipping git pattern mining: not a git repository"
        )
    else:
        logger.info("Phase 3: git pattern mining")
        try:
            mining = mine_git_patterns(
                project_root,
                conn,
                days=mining_days,
                fragile_threshold=fragile_threshold,
                cochange_threshold=cochange_threshold,
            )
            result.fragile_areas_created = mining.fragile_areas_created
            result.cochange_patterns_created = mining.cochange_patterns_created
            result.commits_analyzed = mining.commits_analyzed
            result.files_analyzed = mining.files_analyzed
            logger.info(
                "Git mining complete: %d fragile areas, %d co-change patterns",
                result.fragile_areas_created,
                result.cochange_patterns_created,
            )
        except Exception:
            logger.error("Git pattern mining phase failed", exc_info=True)
            result.phases_errored.append("mining")

    # -------------------------------------------------------------------------
    # Phase 4: LLM Code Analysis
    # Requirement: 101-REQ-5.4
    # -------------------------------------------------------------------------
    if skip_code_analysis:
        result.phases_skipped.append("code_analysis")
        logger.info("Skipping code analysis phase (--skip-code-analysis)")
    else:
        logger.info("Phase 4: LLM code analysis")
        try:
            code_result = await analyze_code_with_llm(
                project_root,
                conn,
                model=model,
                max_files=max_files,
            )
            result.code_facts_created = code_result.facts_created
            result.code_files_analyzed = code_result.files_analyzed
            result.code_files_skipped = code_result.files_skipped
            logger.info(
                "Code analysis complete: %d facts from %d files",
                result.code_facts_created,
                result.code_files_analyzed,
            )
        except Exception:
            logger.error("Code analysis phase failed", exc_info=True)
            result.phases_errored.append("code_analysis")

    # -------------------------------------------------------------------------
    # Phase 5: LLM Documentation Mining
    # Requirement: 101-REQ-6.3
    # -------------------------------------------------------------------------
    if skip_doc_mining:
        result.phases_skipped.append("doc_mining")
        logger.info("Skipping doc mining phase (--skip-doc-mining)")
    else:
        logger.info("Phase 5: LLM documentation mining")
        try:
            doc_result = await mine_docs_with_llm(
                project_root,
                conn,
                model=model,
            )
            result.doc_facts_created = doc_result.facts_created
            result.docs_analyzed = doc_result.docs_analyzed
            result.docs_skipped = doc_result.docs_skipped
            logger.info(
                "Doc mining complete: %d facts from %d docs",
                result.doc_facts_created,
                result.docs_analyzed,
            )
        except Exception:
            logger.error("Documentation mining phase failed", exc_info=True)
            result.phases_errored.append("doc_mining")

    # -------------------------------------------------------------------------
    # Phase 6: Embedding Generation
    # Requirements: 101-REQ-7.1, 101-REQ-7.2, 101-REQ-7.E1
    # -------------------------------------------------------------------------
    if skip_embeddings:
        result.phases_skipped.append("embeddings")
        logger.info("Skipping embedding phase (--skip-embeddings)")
    else:
        logger.info("Phase 6: embedding generation")
        try:
            embedder = EmbeddingGenerator(config.knowledge)
            generated, failed = _generate_missing_embeddings(conn, embedder)
            result.embeddings_generated = generated
            result.embeddings_failed = failed
            logger.info(
                "Embedding phase complete: %d generated, %d failed",
                result.embeddings_generated,
                result.embeddings_failed,
            )
        except Exception:
            logger.error("Embedding phase failed", exc_info=True)
            result.phases_errored.append("embeddings")

    result.elapsed_seconds = time.monotonic() - start_time
    logger.info(
        "Onboarding complete in %.1fs (skipped=%s, errored=%s)",
        result.elapsed_seconds,
        result.phases_skipped,
        result.phases_errored,
    )
    return result
