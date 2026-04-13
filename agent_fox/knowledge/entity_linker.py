"""Fact-entity linking via git diff.

Links facts to the files they affected using the fact's commit_sha
to determine which files were changed.

Requirements: 95-REQ-5.*

NOTE: This module is a stub pending task group 4 implementation.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from agent_fox.knowledge.entities import LinkResult
from agent_fox.knowledge.facts import Fact


def _extract_paths_from_diff(commit_sha: str, repo_root: Path) -> list[str]:
    """Run git diff-tree to extract file paths changed by a commit.

    Returns a list of repo-relative file paths affected by the commit.
    Raises subprocess.CalledProcessError if the commit is not found.

    Requirements: 95-REQ-5.1
    """
    raise NotImplementedError("entity_linker._extract_paths_from_diff: pending task group 4")


def link_facts(
    conn: duckdb.DuckDBPyConnection,
    facts: list[Fact],
    repo_root: Path,
) -> LinkResult:
    """Link facts to file entities via git diff for each fact's commit_sha.

    For each fact with a non-null commit_sha, runs git diff to extract the
    list of affected file paths, looks up corresponding file entities in
    entity_graph, and creates fact_entities links for each match.

    Facts with null commit_sha are skipped (increments facts_skipped).
    Facts with an invalid commit_sha are skipped with a warning.

    Returns a LinkResult with counts.

    Requirements: 95-REQ-5.1, 95-REQ-5.2, 95-REQ-5.3, 95-REQ-5.4,
                  95-REQ-5.E1, 95-REQ-5.E2
    """
    raise NotImplementedError("entity_linker.link_facts: pending task group 4")
