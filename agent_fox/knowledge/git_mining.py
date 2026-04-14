"""Git pattern mining for knowledge onboarding.

Analyzes git history to identify fragile areas (high-churn files) and
co-change patterns (frequently co-modified file pairs). Results are stored
as facts in the knowledge store using fingerprint keywords for idempotency.

Requirements: 101-REQ-4.1, 101-REQ-4.2, 101-REQ-4.3, 101-REQ-4.4,
              101-REQ-4.5, 101-REQ-4.6, 101-REQ-4.E1, 101-REQ-4.E2,
              101-REQ-4.E3
"""

from __future__ import annotations

import itertools
import logging
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from agent_fox.knowledge.facts import Fact

logger = logging.getLogger("agent_fox.knowledge.git_mining")

# Minimum number of commits required to run pattern mining.
# Requirements: 101-REQ-4.E2
_MIN_COMMITS = 10


@dataclass(frozen=True)
class MiningResult:
    """Result of git pattern mining.

    Requirement: 101-REQ-4.6
    """

    fragile_areas_created: int = 0
    cochange_patterns_created: int = 0
    commits_analyzed: int = 0
    files_analyzed: int = 0


def mine_git_patterns(
    project_root: Path,
    conn: duckdb.DuckDBPyConnection,
    *,
    days: int = 365,
    fragile_threshold: int = 20,
    cochange_threshold: int = 5,
) -> MiningResult:
    """Extract fragile areas and co-change patterns from git history.

    Analyzes the most recent *days* days of git history, identifies files
    modified at or above *fragile_threshold* commits (fragile areas) and
    file pairs co-modified at or above *cochange_threshold* commits
    (coupling patterns). Creates facts for each qualifying case, skipping
    duplicates via fingerprint keywords.

    Args:
        project_root: Root directory of the git repository.
        conn: DuckDB connection with knowledge schema (must have keywords column).
        days: Number of days of history to analyze (default: 365).
        fragile_threshold: Min commits to flag a file as fragile (default: 20).
        cochange_threshold: Min co-occurrences for a co-change pattern (default: 5).

    Returns:
        MiningResult with counts of facts created and history analyzed.

    Requirements: 101-REQ-4.1, 101-REQ-4.2, 101-REQ-4.3, 101-REQ-4.4,
                  101-REQ-4.5, 101-REQ-4.E1, 101-REQ-4.E2, 101-REQ-4.E3
    """
    commit_files = _parse_git_numstat(project_root, days)
    commits_total = len(commit_files)

    file_frequencies = _compute_file_frequencies(commit_files)
    cochange_counts = _compute_cochange_counts(commit_files)

    unique_files: set[str] = set()
    for files in commit_files.values():
        unique_files.update(files)

    # Fragile area detection requires a minimum commit history to be meaningful.
    # With too few commits even moderate churn looks extreme, producing noise.
    # Co-change pattern detection has no minimum: coupling signals remain valid
    # with small commit counts (e.g. a 6-commit feature branch).
    # Requirements: 101-REQ-4.E2
    fragile_created = 0
    if commits_total < _MIN_COMMITS:
        logger.info(
            "Insufficient git history: %d commits (need >= %d) for fragile area "
            "detection; skipping fragile area mining",
            commits_total,
            _MIN_COMMITS,
        )
    else:
        for file_path, count in file_frequencies.items():
            if count < fragile_threshold:
                continue
            fingerprint = f"onboard:fragile:{file_path}"
            if _is_mining_fact_exists(conn, fingerprint):
                logger.debug("Skipping duplicate fragile_area fact for %s", file_path)
                continue
            fact = Fact(
                id=str(uuid.uuid4()),
                content=(
                    f"Fragile area: {file_path} was modified in {count} commits "
                    f"over the past {days} days, indicating high churn."
                ),
                category="fragile_area",
                spec_name="onboard",
                keywords=[fingerprint, file_path, "fragile", "churn"],
                confidence=0.6,
                created_at=datetime.now(UTC).isoformat(),
            )
            _write_fact(conn, fact)
            fragile_created += 1
            logger.info("Created fragile_area fact for %s (%d commits)", file_path, count)

    cochange_created = 0
    for (file_a, file_b), count in cochange_counts.items():
        if count < cochange_threshold:
            continue
        fingerprint = f"onboard:cochange:{file_a}:{file_b}"
        if _is_mining_fact_exists(conn, fingerprint):
            logger.debug("Skipping duplicate co-change fact for %s <-> %s", file_a, file_b)
            continue
        fact = Fact(
            id=str(uuid.uuid4()),
            content=(
                f"Co-change pattern: {file_a} and {file_b} were modified together "
                f"in {count} commits, suggesting coupling."
            ),
            category="pattern",
            spec_name="onboard",
            keywords=[fingerprint, file_a, file_b, "coupling"],
            confidence=0.6,
            created_at=datetime.now(UTC).isoformat(),
        )
        _write_fact(conn, fact)
        cochange_created += 1
        logger.info(
            "Created co-change pattern fact for %s <-> %s (%d commits)",
            file_a,
            file_b,
            count,
        )

    return MiningResult(
        fragile_areas_created=fragile_created,
        cochange_patterns_created=cochange_created,
        commits_analyzed=commits_total,
        files_analyzed=len(unique_files),
    )


def _parse_git_numstat(project_root: Path, days: int) -> dict[str, list[str]]:
    """Parse git log --numstat output into a commit→files mapping.

    Runs ``git log --numstat --format=%H --after=N.days.ago`` and parses
    each commit SHA and its changed files. Binary files (shown as ``- -
    filename``) are excluded.

    Args:
        project_root: Directory to run git in.
        days: Number of days back to query.

    Returns:
        dict mapping commit SHA → list of changed file paths.

    Requirements: 101-REQ-4.3
    """
    since_arg = f"--after={days}.days.ago"
    result = subprocess.run(
        ["git", "log", "--numstat", "--format=%H", since_arg],
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.warning("git log --numstat failed (exit %d): %s", result.returncode, result.stderr)
        return {}

    commit_files: dict[str, list[str]] = {}
    current_sha: str | None = None

    for line in result.stdout.splitlines():
        stripped = line.rstrip()
        if not stripped:
            continue

        parts = stripped.split("\t")
        if len(parts) >= 3:
            # Numstat line: <added>\t<removed>\t<filename>
            added, removed = parts[0], parts[1]
            filename = "\t".join(parts[2:])
            if added == "-" and removed == "-":
                continue  # binary file, skip
            if current_sha is not None:
                commit_files.setdefault(current_sha, []).append(filename)
        elif "\t" not in stripped:
            # SHA line: no tabs, just the commit hash
            current_sha = stripped
            commit_files.setdefault(current_sha, [])

    return commit_files


def _compute_file_frequencies(commit_files: dict[str, list[str]]) -> dict[str, int]:
    """Count how many commits touched each file.

    Args:
        commit_files: dict mapping commit SHA → list of file paths.

    Returns:
        dict mapping file path → number of commits that touched it.

    Requirement: 101-REQ-4.1
    """
    frequencies: dict[str, int] = {}
    for files in commit_files.values():
        for file in files:
            frequencies[file] = frequencies.get(file, 0) + 1
    return frequencies


def _compute_cochange_counts(
    commit_files: dict[str, list[str]],
) -> dict[tuple[str, str], int]:
    """Count co-occurrences for every pair of files changed in the same commit.

    Keys are sorted tuples (file_a, file_b) where file_a < file_b
    lexicographically, ensuring each pair is counted only once regardless
    of the order files appear in a commit.

    Args:
        commit_files: dict mapping commit SHA → list of file paths.

    Returns:
        dict mapping (file_a, file_b) → number of commits with both files.

    Requirement: 101-REQ-4.2
    """
    counts: dict[tuple[str, str], int] = {}
    for files in commit_files.values():
        if len(files) < 2:
            continue
        # Sort files so (a, b) always has a <= b lexicographically
        for pair in itertools.combinations(sorted(files), 2):
            counts[pair] = counts.get(pair, 0) + 1
    return counts


def _is_mining_fact_exists(conn: duckdb.DuckDBPyConnection, fingerprint: str) -> bool:
    """Check if a fact with this fingerprint keyword already exists in DuckDB.

    Uses DuckDB's ``list_contains()`` function to search the ``keywords``
    TEXT[] column. Returns True if any active (non-superseded) fact has the
    given fingerprint in its keywords list.

    Args:
        conn: DuckDB connection with memory_facts table.
        fingerprint: Fingerprint keyword string to look up.

    Returns:
        True if the fingerprint exists, False otherwise.

    Requirement: 101-REQ-4.E3
    """
    result = conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE list_contains(keywords, ?)",
        [fingerprint],
    ).fetchone()
    return result is not None and result[0] > 0


def _write_fact(conn: duckdb.DuckDBPyConnection, fact: Fact) -> None:
    """Write a Fact directly to the DuckDB memory_facts table.

    Uses INSERT OR IGNORE so duplicate fact IDs are silently dropped.
    Does not generate embeddings (best-effort embedding generation is
    handled by the onboard orchestrator's embedding phase).

    Args:
        conn: DuckDB connection with memory_facts table (keywords column required).
        fact: Fact to persist.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO memory_facts
            (id, content, category, spec_name, session_id,
             commit_sha, confidence, created_at, keywords)
        VALUES (?::UUID, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """,
        [
            fact.id,
            fact.content,
            fact.category,
            fact.spec_name,
            fact.session_id,
            fact.commit_sha,
            fact.confidence,
            fact.keywords if fact.keywords else [],
        ],
    )
