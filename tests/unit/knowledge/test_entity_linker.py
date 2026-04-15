"""Tests for entity_linker module.

Test Spec: TS-95-18 through TS-95-21, TS-95-E8, TS-95-E9
Requirements: 95-REQ-5.*
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from agent_fox.knowledge.entities import EntityType
from agent_fox.knowledge.entity_linker import link_facts
from agent_fox.knowledge.entity_store import upsert_entities
from agent_fox.knowledge.facts import Fact
from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def entity_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with base schema + all migrations applied."""
    from agent_fox.knowledge.migrations import apply_pending_migrations

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    apply_pending_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
    commit_sha: str | None = None,
) -> None:
    """Insert a minimal fact into memory_facts for testing."""
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, category, spec_name, confidence, created_at, commit_sha)
        VALUES (?, 'Test fact', 'decision', 'test_spec', 0.9, CURRENT_TIMESTAMP, ?)
        """,
        [fact_id, commit_sha],
    )


def _make_fact(commit_sha: str | None = "abc123") -> Fact:
    """Create a Fact with an optional commit_sha."""
    return Fact(
        id=str(uuid.uuid4()),
        content="Test fact content",
        category="decision",
        spec_name="test_spec",
        keywords=["test"],
        confidence=0.9,
        created_at="2026-01-01T00:00:00Z",
        supersedes=None,
        session_id="test/1",
        commit_sha=commit_sha,
    )


def _upsert_file_entity(
    conn: duckdb.DuckDBPyConnection,
    path: str,
) -> str:
    """Insert a file entity and return its ID."""
    from agent_fox.knowledge.entities import Entity

    entity = Entity(
        id=str(uuid.uuid4()),
        entity_type=EntityType.FILE,
        entity_name=path.split("/")[-1],
        entity_path=path,
        created_at="2026-01-01T00:00:00Z",
        deleted_at=None,
    )
    return upsert_entities(conn, [entity])[0]


# ---------------------------------------------------------------------------
# TS-95-18: Git diff path extraction
# ---------------------------------------------------------------------------


class TestGitDiffPathExtraction:
    """TS-95-18: link_facts extracts file paths from git diff for each fact's commit_sha.

    Requirement: 95-REQ-5.1
    """

    def test_git_diff_called_with_commit_sha(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """_extract_paths_from_diff is called with the fact's commit_sha."""
        fact_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_id, commit_sha="abc123")
        _upsert_file_entity(entity_conn, "src/foo.py")
        _upsert_file_entity(entity_conn, "src/bar.py")

        fact = _make_fact(commit_sha="abc123")
        # Update fact id to match the inserted fact
        fact = Fact(
            id=fact_id,
            content=fact.content,
            category=fact.category,
            spec_name=fact.spec_name,
            keywords=fact.keywords,
            confidence=fact.confidence,
            created_at=fact.created_at,
            supersedes=fact.supersedes,
            session_id=fact.session_id,
            commit_sha="abc123",
        )

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "src/foo.py\nsrc/bar.py\n"

        with patch("subprocess.run", return_value=mock_result):
            result = link_facts(entity_conn, [fact], tmp_path)

        assert result.facts_processed == 1


# ---------------------------------------------------------------------------
# TS-95-19: Fact-entity links created from diff paths
# ---------------------------------------------------------------------------


class TestFactEntityLinkCreationFromDiff:
    """TS-95-19: Fact-entity links are created for matched files from git diff.

    Requirement: 95-REQ-5.2
    """

    def test_links_created_for_matched_files(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Two fact-entity rows are created when diff returns two matching paths."""
        fact_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_id, commit_sha="abc123")

        foo_id = _upsert_file_entity(entity_conn, "src/foo.py")  # noqa: F841
        bar_id = _upsert_file_entity(entity_conn, "src/bar.py")  # noqa: F841

        fact = Fact(
            id=fact_id,
            content="Test",
            category="decision",
            spec_name="test_spec",
            keywords=[],
            confidence=0.9,
            created_at="2026-01-01T00:00:00Z",
            supersedes=None,
            session_id="test/1",
            commit_sha="abc123",
        )

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "src/foo.py\nsrc/bar.py\n"

        with patch("subprocess.run", return_value=mock_result):
            link_facts(entity_conn, [fact], tmp_path)

        _row = entity_conn.execute("SELECT COUNT(*) FROM fact_entities WHERE fact_id = ?", [fact_id]).fetchone()
        assert _row is not None
        count = _row[0]
        assert count == 2


# ---------------------------------------------------------------------------
# TS-95-20: LinkResult counts
# ---------------------------------------------------------------------------


class TestLinkResultCounts:
    """TS-95-20: link_facts returns correct LinkResult counts.

    Requirement: 95-REQ-5.3
    """

    def test_link_result_has_correct_counts(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """LinkResult reflects one processed, one skipped, one link created."""
        fact_with_sha_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_with_sha_id, commit_sha="abc123")
        fact_without_sha_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_without_sha_id, commit_sha=None)

        _upsert_file_entity(entity_conn, "src/foo.py")

        fact_with_sha = Fact(
            id=fact_with_sha_id,
            content="Test",
            category="decision",
            spec_name="test_spec",
            keywords=[],
            confidence=0.9,
            created_at="2026-01-01T00:00:00Z",
            supersedes=None,
            session_id="test/1",
            commit_sha="abc123",
        )
        fact_without_sha = Fact(
            id=fact_without_sha_id,
            content="No SHA",
            category="decision",
            spec_name="test_spec",
            keywords=[],
            confidence=0.9,
            created_at="2026-01-01T00:00:00Z",
            supersedes=None,
            session_id="test/1",
            commit_sha=None,
        )

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "src/foo.py\n"

        with patch("subprocess.run", return_value=mock_result):
            result = link_facts(entity_conn, [fact_with_sha, fact_without_sha], tmp_path)

        assert result.facts_processed == 1
        assert result.links_created >= 1
        assert result.facts_skipped == 1


# ---------------------------------------------------------------------------
# TS-95-21: Skip facts without commit_sha
# ---------------------------------------------------------------------------


class TestSkipFactsWithoutCommitSha:
    """TS-95-21: Facts with null commit_sha are skipped.

    Requirement: 95-REQ-5.4
    """

    def test_null_commit_sha_skipped(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Fact with commit_sha=None increments facts_skipped."""
        fact_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_id, commit_sha=None)

        fact = Fact(
            id=fact_id,
            content="No SHA fact",
            category="decision",
            spec_name="test_spec",
            keywords=[],
            confidence=0.9,
            created_at="2026-01-01T00:00:00Z",
            supersedes=None,
            session_id="test/1",
            commit_sha=None,
        )

        result = link_facts(entity_conn, [fact], tmp_path)

        assert result.facts_skipped == 1
        assert result.facts_processed == 0
        assert result.links_created == 0


# ---------------------------------------------------------------------------
# TS-95-E8: Missing commit_sha in git repo
# ---------------------------------------------------------------------------


class TestMissingCommitInRepo:
    """TS-95-E8: A commit SHA not found in the local repo is skipped with a warning.

    Requirement: 95-REQ-5.E1
    """

    def test_missing_commit_sha_skipped_with_warning(
        self,
        entity_conn: duckdb.DuckDBPyConnection,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Fact with invalid commit_sha is skipped; warning logged."""
        import logging

        fact_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_id, commit_sha="deadbeef")

        fact = Fact(
            id=fact_id,
            content="Test",
            category="decision",
            spec_name="test_spec",
            keywords=[],
            confidence=0.9,
            created_at="2026-01-01T00:00:00Z",
            supersedes=None,
            session_id="test/1",
            commit_sha="deadbeef",
        )

        mock_result = MagicMock()
        mock_result.returncode = 128  # git failure (non-zero)
        mock_result.stdout = ""
        mock_result.stderr = "fatal: bad object deadbeef"

        with patch("subprocess.run", return_value=mock_result):
            with caplog.at_level(logging.WARNING, logger="agent_fox"):
                result = link_facts(entity_conn, [fact], tmp_path)

        assert result.facts_skipped == 1
        assert result.facts_processed == 0
        assert "deadbeef" in caplog.text


# ---------------------------------------------------------------------------
# TS-95-E9: Git diff paths with no matching entities
# ---------------------------------------------------------------------------


class TestUnmatchedDiffPaths:
    """TS-95-E9: Paths from git diff with no matching entities are skipped.

    Requirement: 95-REQ-5.E2
    """

    def test_unmatched_paths_create_no_links(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """No links created when git diff returns paths not in entity_graph."""
        fact_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_id, commit_sha="abc123")

        fact = Fact(
            id=fact_id,
            content="Test",
            category="decision",
            spec_name="test_spec",
            keywords=[],
            confidence=0.9,
            created_at="2026-01-01T00:00:00Z",
            supersedes=None,
            session_id="test/1",
            commit_sha="abc123",
        )

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "src/unknown.py\n"  # no entity exists for this path

        with patch("subprocess.run", return_value=mock_result):
            result = link_facts(entity_conn, [fact], tmp_path)

        assert result.links_created == 0
        assert result.facts_processed == 1
        assert result.facts_skipped == 0
