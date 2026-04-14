"""LLM code analysis for knowledge onboarding.

Analyzes source files with LLM to extract architectural knowledge:
decisions, conventions, patterns, anti-patterns, fragile areas, and gotchas.
Results are stored as facts in the knowledge store with fingerprint keywords
for idempotent re-runs.

Requirements: 101-REQ-5.1, 101-REQ-5.2, 101-REQ-5.3, 101-REQ-5.5,
              101-REQ-5.6, 101-REQ-5.E1, 101-REQ-5.E2, 101-REQ-5.E3
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from agent_fox.core.client import ai_call
from agent_fox.knowledge.facts import Category, Fact, parse_confidence
from agent_fox.knowledge.git_mining import _is_mining_fact_exists, _write_fact

logger = logging.getLogger("agent_fox.knowledge.code_analysis")

# ---------------------------------------------------------------------------
# System prompt for LLM code analysis
# ---------------------------------------------------------------------------

CODE_ANALYSIS_PROMPT = """You are analyzing source code from an existing software project to extract \
architectural knowledge. For each file, identify:

- **Decisions**: Architectural choices (e.g., "uses dependency injection", \
"event-driven architecture", "repository pattern for data access").
- **Conventions**: Coding standards and naming conventions (e.g., "all \
handlers follow async/await pattern", "error types use Error suffix").
- **Patterns**: Recurring design patterns (e.g., "factory pattern for \
creating services", "decorator pattern for cross-cutting concerns").
- **Anti-patterns**: Code smells or problematic patterns (e.g., "god class \
with too many responsibilities", "circular dependency between modules").
- **Fragile areas**: Code that appears fragile or risky (e.g., "complex \
conditional logic", "tightly coupled to external API").
- **Gotchas**: Non-obvious behaviors or traps (e.g., "silent exception \
swallowing", "order-dependent initialization").

Return a JSON array. Each element has: "content" (description), "category" \
(one of: decision, convention, pattern, anti_pattern, fragile_area, gotcha), \
"confidence" (high/medium/low), "keywords" (2-5 relevant terms).

Only report findings that are genuinely useful to a developer working in \
this codebase for the first time. Prefer fewer high-quality facts over \
many shallow observations."""

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Recognized source file extensions for all supported languages.
#: Requirements: 101-REQ-5.1
SOURCE_EXTENSIONS: set[str] = {
    ".py", ".go", ".rs", ".ts", ".tsx", ".js", ".jsx",
    ".java", ".kt", ".kts", ".swift", ".c", ".cpp", ".cc",
    ".cxx", ".h", ".hpp", ".cs", ".rb", ".ex", ".exs",
    ".erl", ".hs", ".ml", ".mli", ".scala", ".clj",
    ".lua", ".php", ".r", ".jl", ".dart", ".zig",
    ".nim", ".v", ".cr", ".sh", ".bash", ".zsh",
}

#: Directories excluded from source file scanning.
_EXCLUDED_DIRS: set[str] = {
    ".git", ".hg", ".svn",
    "node_modules", "vendor", ".venv", "venv", "__pycache__",
    "build", "dist", "target", ".tox", "env", ".env",
}

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodeAnalysisResult:
    """Result of LLM code analysis.

    Requirement: 101-REQ-5.5
    """

    facts_created: int = 0
    files_analyzed: int = 0
    files_skipped: int = 0


# ---------------------------------------------------------------------------
# File scanning helpers
# ---------------------------------------------------------------------------


def _scan_source_files(project_root: Path) -> list[Path]:
    """Scan project root for source files by recognized extensions.

    Excludes common non-source directories: node_modules, vendor, .venv,
    __pycache__, build, dist, target, .git, and any hidden directory.
    Returns files sorted alphabetically by path.

    Args:
        project_root: Root directory to scan.

    Returns:
        List of Path objects sorted alphabetically.

    Requirements: 101-REQ-5.E2
    """
    results: list[Path] = []

    def _walk(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            return
        for entry in entries:
            if entry.is_dir():
                # Skip hidden dirs and common non-source dirs
                if entry.name.startswith(".") or entry.name in _EXCLUDED_DIRS:
                    continue
                _walk(entry)
            elif entry.is_file() and entry.suffix in SOURCE_EXTENSIONS:
                results.append(entry)

    _walk(project_root)
    return results


def _get_files_by_priority(
    conn: duckdb.DuckDBPyConnection,
    project_root: Path,
) -> list[Path]:
    """Get source files ordered by architectural significance.

    Queries the entity graph for file entities sorted by incoming import
    edge count (most-imported first). Falls back to disk scanning if the
    entity graph is empty or the query fails.

    Args:
        conn: DuckDB connection with entity_graph schema.
        project_root: Root directory of the project.

    Returns:
        List of Paths sorted by import importance, or alphabetically on
        fallback.

    Requirements: 101-REQ-5.2, 101-REQ-5.E2
    """
    try:
        rows = conn.execute(
            """
            SELECT eg.entity_path, COUNT(ee.source_id) AS import_count
            FROM entity_graph eg
            LEFT JOIN entity_edges ee
                ON ee.target_id = eg.id AND ee.relationship = 'imports'
            WHERE eg.entity_type = 'file'
              AND eg.deleted_at IS NULL
            GROUP BY eg.id, eg.entity_path
            ORDER BY import_count DESC
            """
        ).fetchall()
    except Exception:
        logger.warning(
            "Entity graph query failed; falling back to disk scan",
            exc_info=True,
        )
        rows = []

    if not rows:
        # No file entities in entity graph — fall back to disk scan.
        # Requirements: 101-REQ-5.E2
        logger.info(
            "Entity graph has no file entities; "
            "falling back to disk scan for file prioritization"
        )
        return _scan_source_files(project_root)

    # Resolve entity paths to absolute paths under project_root.
    files: list[Path] = []
    for entity_path, _import_count in rows:
        candidate = project_root / entity_path
        if candidate.exists() and candidate.is_file():
            files.append(candidate)

    if not files:
        # Entity graph had entries but none matched files on disk — fall back.
        logger.info(
            "Entity graph files not found on disk; falling back to disk scan"
        )
        return _scan_source_files(project_root)

    return files


# ---------------------------------------------------------------------------
# LLM fact parsing
# ---------------------------------------------------------------------------


def _parse_llm_facts(
    raw_text: str,
    spec_name: str,
    file_path: str,
    source_type: str,
) -> list[Fact]:
    """Parse LLM JSON response into Fact objects.

    Expected format: JSON array of objects with keys:
    content, category, confidence, keywords.

    Adds a fingerprint keyword to each fact:
    - source_type "code" → ``"onboard:code:{file_path}"``
    - source_type "doc"  → ``"onboard:doc:{file_path}"``

    Facts with invalid or unrecognized categories are silently dropped.

    Args:
        raw_text: JSON string from LLM.
        spec_name: Spec name for all facts (e.g., ``"onboard"``).
        file_path: Relative path of the analyzed file.
        source_type: ``"code"`` or ``"doc"`` — determines fingerprint prefix.

    Returns:
        List of Fact objects with fingerprint keywords prepended.

    Requirements: 101-REQ-5.1, 101-REQ-5.6
    """
    fingerprint = f"onboard:{source_type}:{file_path}"
    valid_categories = {c.value for c in Category}

    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse LLM response as JSON for %s", file_path)
        return []

    if not isinstance(data, list):
        logger.warning("LLM response for %s is not a JSON array", file_path)
        return []

    facts: list[Fact] = []
    for item in data:
        if not isinstance(item, dict):
            continue

        content = str(item.get("content", "")).strip()
        if not content:
            continue

        category_raw = str(item.get("category", "")).strip()
        if category_raw not in valid_categories:
            logger.debug(
                "Skipping fact with invalid category '%s' for %s",
                category_raw,
                file_path,
            )
            continue

        confidence = parse_confidence(item.get("confidence"))

        llm_keywords = item.get("keywords", [])
        if not isinstance(llm_keywords, list):
            llm_keywords = []

        # Fingerprint keyword is prepended for easy dedup lookup.
        keywords = [fingerprint, *[str(k) for k in llm_keywords]]

        fact = Fact(
            id=str(uuid.uuid4()),
            content=content,
            category=category_raw,
            spec_name=spec_name,
            keywords=keywords,
            confidence=confidence,
            created_at=datetime.now(UTC).isoformat(),
        )
        facts.append(fact)

    return facts


# ---------------------------------------------------------------------------
# Main async orchestrator
# ---------------------------------------------------------------------------


async def analyze_code_with_llm(
    project_root: Path,
    conn: duckdb.DuckDBPyConnection,
    *,
    model: str = "STANDARD",
    max_files: int = 0,
) -> CodeAnalysisResult:
    """Analyze source files with LLM to extract architectural knowledge.

    Reads each source file in priority order (most-imported first when the
    entity graph is available, alphabetical otherwise), sends its content
    to the LLM with the code analysis prompt, parses the structured JSON
    response into facts, and stores them.

    Files already analyzed in a previous onboard run (identified by a
    ``onboard:code:{file_path}`` fingerprint keyword on an existing fact)
    are skipped without re-analysis.

    Per-file LLM failures and unparseable responses are handled gracefully:
    the file is counted as skipped and processing continues.

    Args:
        project_root: Root directory of the project.
        conn: DuckDB connection with knowledge schema (keywords column required).
        model: Model tier for LLM calls (default: ``"STANDARD"``).
        max_files: Maximum files to analyze (0 = no limit).

    Returns:
        CodeAnalysisResult with counts of facts created, files analyzed,
        and files skipped.

    Requirements: 101-REQ-5.1, 101-REQ-5.2, 101-REQ-5.3, 101-REQ-5.5,
                  101-REQ-5.6, 101-REQ-5.E1, 101-REQ-5.E2, 101-REQ-5.E3
    """
    files = _get_files_by_priority(conn, project_root)
    if max_files > 0:
        files = files[:max_files]

    facts_created = 0
    files_analyzed = 0
    files_skipped = 0

    for file_path in files:
        try:
            rel_path = str(file_path.relative_to(project_root))
        except ValueError:
            rel_path = file_path.name

        fingerprint = f"onboard:code:{rel_path}"

        # Deduplication: skip files already analyzed in a previous run.
        # Requirements: 101-REQ-5.6
        if _is_mining_fact_exists(conn, fingerprint):
            logger.debug("Skipping already-analyzed file: %s", rel_path)
            files_skipped += 1
            continue

        try:
            content = file_path.read_text(errors="replace")
        except OSError as exc:
            logger.warning("Failed to read file %s: %s", rel_path, exc)
            files_skipped += 1
            continue

        # Call LLM for code analysis.
        # Requirements: 101-REQ-5.E1
        try:
            raw_text, _raw_response = await ai_call(
                model_tier=model,
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": f"File: {rel_path}\n\n```\n{content}\n```",
                    }
                ],
                system=CODE_ANALYSIS_PROMPT,
                context="onboard code analysis",
            )
        except Exception as exc:
            logger.warning("LLM call failed for %s: %s", rel_path, exc)
            files_skipped += 1
            continue

        if raw_text is None:
            logger.warning("LLM returned no text for %s", rel_path)
            files_skipped += 1
            continue

        # Validate JSON parseability before extracting facts.
        # Requirements: 101-REQ-5.E3
        try:
            json.loads(raw_text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Unparseable LLM response for %s", rel_path)
            files_skipped += 1
            continue

        facts = _parse_llm_facts(
            raw_text,
            spec_name="onboard",
            file_path=rel_path,
            source_type="code",
        )

        for fact in facts:
            _write_fact(conn, fact)
            facts_created += 1

        files_analyzed += 1
        logger.info(
            "Analyzed %s: %d facts created",
            rel_path,
            len(facts),
        )

    return CodeAnalysisResult(
        facts_created=facts_created,
        files_analyzed=files_analyzed,
        files_skipped=files_skipped,
    )
