"""LLM documentation mining for knowledge onboarding.

Reads markdown documentation files and uses an LLM to extract knowledge
(conventions, decisions, patterns, and gotchas). Results are stored as facts
in the knowledge store with fingerprint keywords for idempotent re-runs.

Requirements: 101-REQ-6.1, 101-REQ-6.2, 101-REQ-6.4, 101-REQ-6.5,
              101-REQ-6.6, 101-REQ-6.E1, 101-REQ-6.E2, 101-REQ-6.E3
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb

from agent_fox.core.client import ai_call
from agent_fox.knowledge.code_analysis import _parse_llm_facts
from agent_fox.knowledge.git_mining import _is_mining_fact_exists, _write_fact

logger = logging.getLogger("agent_fox.knowledge.doc_mining")

# ---------------------------------------------------------------------------
# System prompt for LLM documentation mining
# ---------------------------------------------------------------------------

DOC_MINING_PROMPT = """You are analyzing project documentation to extract knowledge for a \
development knowledge base. For each document, identify:

- **Conventions**: Coding standards, workflow rules, naming conventions.
- **Decisions**: Architectural or design decisions with rationale.
- **Patterns**: Recommended approaches or established workflows.
- **Gotchas**: Warnings, caveats, or non-obvious requirements.

Return a JSON array. Each element has: "content" (description), "category" \
(one of: decision, convention, pattern, gotcha), "confidence" \
(high/medium/low), "keywords" (2-5 relevant terms).

Focus on actionable knowledge that helps a developer understand how to \
work in this project. Skip boilerplate, license text, and generic \
information."""

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocMiningResult:
    """Result of LLM documentation mining.

    Requirement: 101-REQ-6.4
    """

    facts_created: int = 0
    docs_analyzed: int = 0
    docs_skipped: int = 0


# ---------------------------------------------------------------------------
# Document collection helper
# ---------------------------------------------------------------------------


def _collect_doc_files(project_root: Path) -> list[Path]:
    """Collect markdown documentation files for mining.

    Includes:
    - README.md, CONTRIBUTING.md, CHANGELOG.md at project root (if present).
    - All *.md files under docs/ — excluding docs/adr/ and docs/errata/.

    Returns files in a stable order (root files first, then docs/ files
    sorted alphabetically by path).

    Args:
        project_root: Root directory of the project.

    Returns:
        List of Path objects for discovered markdown files.

    Requirement: 101-REQ-6.2
    """
    files: list[Path] = []

    # Root-level docs: README.md, CONTRIBUTING.md, CHANGELOG.md
    for name in ("README.md", "CONTRIBUTING.md", "CHANGELOG.md"):
        candidate = project_root / name
        # Security: reject symlinks to prevent path traversal (CWE-59)
        if candidate.is_symlink():
            logger.warning("Skipping root-level symlink for security: %s", candidate)
            continue
        if candidate.is_file():
            files.append(candidate)

    # docs/**/*.md, excluding docs/adr/ and docs/errata/
    docs_dir = project_root / "docs"
    if docs_dir.is_dir():
        adr_dir = docs_dir / "adr"
        errata_dir = docs_dir / "errata"
        resolved_docs_dir = docs_dir.resolve()
        for md_file in sorted(docs_dir.rglob("*.md")):
            # Security: reject symlinks that escape the docs/ boundary (CWE-59)
            if md_file.is_symlink():
                try:
                    md_file.resolve().relative_to(resolved_docs_dir)
                except ValueError:
                    logger.warning("Skipping symlink pointing outside docs/: %s", md_file)
                    continue
            # Skip files inside excluded subdirectories
            try:
                md_file.relative_to(adr_dir)
                continue  # inside docs/adr/ — skip
            except ValueError:
                pass
            try:
                md_file.relative_to(errata_dir)
                continue  # inside docs/errata/ — skip
            except ValueError:
                pass
            files.append(md_file)

    return files


# ---------------------------------------------------------------------------
# Main async orchestrator
# ---------------------------------------------------------------------------


async def mine_docs_with_llm(
    project_root: Path,
    conn: duckdb.DuckDBPyConnection,
    *,
    model: str = "STANDARD",
) -> DocMiningResult:
    """Mine project documentation with LLM to extract knowledge.

    Reads markdown files (README, CONTRIBUTING, docs/*.md excluding ADRs and
    errata), sends each to the LLM with a documentation analysis prompt,
    parses the structured JSON response into facts, and stores them.

    Documents already mined in a previous onboard run (identified by a
    ``onboard:doc:{doc_path}`` fingerprint keyword on an existing fact) are
    skipped without re-analysis.

    Per-document LLM failures and unparseable responses are handled
    gracefully: the document is counted as skipped and processing continues.

    Args:
        project_root: Root directory of the project.
        conn: DuckDB connection with knowledge schema (keywords column required).
        model: Model tier for LLM calls (default: ``"STANDARD"``).

    Returns:
        DocMiningResult with counts of facts created, docs analyzed,
        and docs skipped.

    Requirements: 101-REQ-6.1, 101-REQ-6.2, 101-REQ-6.4, 101-REQ-6.5,
                  101-REQ-6.6, 101-REQ-6.E1, 101-REQ-6.E2, 101-REQ-6.E3
    """
    doc_files = _collect_doc_files(project_root)

    if not doc_files:
        # Requirement: 101-REQ-6.E2
        logger.info("No documentation files found in %s; skipping doc mining phase", project_root)
        return DocMiningResult()

    facts_created = 0
    docs_analyzed = 0
    docs_skipped = 0

    for doc_path in doc_files:
        try:
            rel_path = str(doc_path.relative_to(project_root))
        except ValueError:
            rel_path = doc_path.name

        fingerprint = f"onboard:doc:{rel_path}"

        # Deduplication: skip docs already mined in a previous run.
        # Requirement: 101-REQ-6.6
        if _is_mining_fact_exists(conn, fingerprint):
            logger.debug("Skipping already-mined document: %s", rel_path)
            docs_skipped += 1
            continue

        try:
            content = doc_path.read_text(errors="replace")
        except OSError as exc:
            logger.warning("Failed to read document %s: %s", rel_path, exc)
            docs_skipped += 1
            continue

        # Call LLM for documentation analysis.
        # Requirement: 101-REQ-6.E1
        try:
            raw_text, _raw_response = await ai_call(
                model_tier=model,
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": f"Document: {rel_path}\n\n{content}",
                    }
                ],
                system=DOC_MINING_PROMPT,
                context="onboard doc mining",
            )
        except Exception as exc:
            logger.warning("LLM call failed for document %s: %s", rel_path, exc)
            docs_skipped += 1
            continue

        if raw_text is None:
            logger.warning("LLM returned no text for document %s", rel_path)
            docs_skipped += 1
            continue

        # Validate JSON parseability before extracting facts.
        # Requirement: 101-REQ-6.E3
        try:
            json.loads(raw_text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Unparseable LLM response for document %s", rel_path)
            docs_skipped += 1
            continue

        facts = _parse_llm_facts(
            raw_text,
            spec_name="onboard",
            file_path=rel_path,
            source_type="doc",
        )

        for fact in facts:
            _write_fact(conn, fact)
            facts_created += 1

        docs_analyzed += 1
        logger.info(
            "Mined %s: %d facts created",
            rel_path,
            len(facts),
        )

    return DocMiningResult(
        facts_created=facts_created,
        docs_analyzed=docs_analyzed,
        docs_skipped=docs_skipped,
    )
