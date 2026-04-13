"""Fact-entity linking via git diff.

Links facts to the files they affected using the fact's commit_sha
to determine which files were changed.

Requirements: 95-REQ-5.*
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import duckdb

from agent_fox.knowledge.entities import LinkResult
from agent_fox.knowledge.entity_store import create_fact_entity_links, find_entities_by_paths
from agent_fox.knowledge.facts import Fact

logger = logging.getLogger(__name__)


def _extract_paths_from_diff(commit_sha: str, repo_root: Path) -> list[str]:
    """Run git diff-tree to extract file paths changed by a commit.

    Uses ``git diff-tree --no-commit-id --name-only -r <sha>`` which
    lists files changed by the commit compared to its parent(s).

    Returns a list of repo-relative file paths affected by the commit.
    Raises RuntimeError if the git command exits with a non-zero return code
    (e.g. because the commit SHA does not exist in the local repository).

    Requirements: 95-REQ-5.1
    """
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git diff-tree failed for commit {commit_sha!r} (returncode={result.returncode}): {result.stderr.strip()}"
        )
    paths = [p.strip() for p in result.stdout.splitlines() if p.strip()]
    return paths


def link_facts(
    conn: duckdb.DuckDBPyConnection,
    facts: list[Fact],
    repo_root: Path,
) -> LinkResult:
    """Link facts to file entities via git diff for each fact's commit_sha.

    For each fact with a non-null commit_sha, runs git diff-tree to extract
    the list of affected file paths, looks up corresponding file entities in
    entity_graph, and creates fact_entities links for each match.

    Facts with null commit_sha are skipped (increments facts_skipped).
    Facts with an invalid/missing commit_sha are skipped with a WARNING log.
    Diff paths with no matching entity in entity_graph are silently skipped.

    Returns a LinkResult with counts:
    - facts_processed: facts with commit_sha where git diff succeeded
    - links_created: total fact_entity rows created or attempted
    - facts_skipped: facts with null commit_sha or failed git diff

    Requirements: 95-REQ-5.1, 95-REQ-5.2, 95-REQ-5.3, 95-REQ-5.4,
                  95-REQ-5.E1, 95-REQ-5.E2
    """
    facts_processed = 0
    links_created = 0
    facts_skipped = 0

    for fact in facts:
        # 95-REQ-5.4: skip facts with no commit_sha
        if fact.commit_sha is None:
            facts_skipped += 1
            continue

        # 95-REQ-5.1: extract affected paths from git diff
        try:
            paths = _extract_paths_from_diff(fact.commit_sha, repo_root)
        except Exception as exc:
            # 95-REQ-5.E1: log warning and skip if commit not found
            logger.warning(
                "Skipping fact %s: could not extract diff for commit %s: %s",
                fact.id,
                fact.commit_sha,
                exc,
            )
            facts_skipped += 1
            continue

        # 95-REQ-5.2: look up matching file entities by path
        entities = find_entities_by_paths(conn, paths)
        entity_ids = [e.id for e in entities]

        # 95-REQ-5.E2: unmatched paths are skipped silently (entity_ids may be empty)
        if entity_ids:
            n = create_fact_entity_links(conn, fact.id, entity_ids)
            links_created += n

        facts_processed += 1

    return LinkResult(
        facts_processed=facts_processed,
        links_created=links_created,
        facts_skipped=facts_skipped,
    )
