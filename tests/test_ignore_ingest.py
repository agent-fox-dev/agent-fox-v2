"""Tests for af:ignore knowledge ingestion pipeline.

Test cases: TS-110-12, TS-110-13, TS-110-17, TS-110-E5 through TS-110-E7,
TS-110-P6, TS-110-SMOKE-2

Requirements: 110-REQ-5.1 through 110-REQ-5.E3
"""

from __future__ import annotations

import asyncio

import pytest

# These imports will fail until task group 5 implements ignore_ingest.py.
# All tests in this file will error on collection until then.
from agent_fox.nightshift.ignore_ingest import (
    extract_category_from_body,
    ingest_ignore_signals,
)
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.platform.protocol import IssueResult

# Marker that indicates an issue body has been ingested into the knowledge store.
_KNOWLEDGE_INGESTED_MARKER = "<!-- af:knowledge-ingested -->"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(
    number: int = 1,
    title: str = "Dead code: unused_fn",
    body: str | None = None,
    with_marker: bool = False,
    category: str = "dead_code",
) -> IssueResult:
    """Create an af:ignore IssueResult for testing."""
    if body is None:
        body = (
            f"## {title}\n\n"
            f"**Category:** {category}\n\n"
            "**Severity:** minor\n\n"
            "This finding was marked as a false positive."
        )
    if with_marker:
        body = body + f"\n{_KNOWLEDGE_INGESTED_MARKER}"
    return IssueResult(
        number=number,
        title=title,
        html_url=f"https://github.com/org/repo/issues/{number}",
        body=body,
    )


class _SameVectorEmbedder:
    """Returns the same vector for all texts."""

    def __init__(self, vector: list[float] | None = None) -> None:
        self._vector = vector or [1.0, 0.0, 0.0]
        self.embed_batch_call_count = 0

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        self.embed_batch_call_count += 1
        return [list(self._vector) for _ in texts]


class _MockPlatform:
    """Mock platform for ingestion tests."""

    def __init__(
        self,
        ignore_issues: list[IssueResult] | None = None,
        update_raises: bool = False,
        list_raises: bool = False,
    ) -> None:
        self._ignore_issues: list[IssueResult] = ignore_issues or []
        self._update_raises = update_raises
        self._list_raises = list_raises
        self.update_issue_calls: list[dict[str, object]] = []
        self.list_issues_calls: list[dict[str, str]] = []

    async def list_issues_by_label(
        self, label: str, state: str = "open", **kwargs: object
    ) -> list[IssueResult]:
        self.list_issues_calls.append({"label": label, "state": state})
        if self._list_raises:
            raise RuntimeError("Platform list failure (test)")
        if label == "af:ignore":
            return list(self._ignore_issues)
        return []

    async def update_issue(self, issue_number: int, body: str) -> None:
        self.update_issue_calls.append({"number": issue_number, "body": body})
        if self._update_raises:
            raise RuntimeError("Platform update failure (test)")

    async def create_issue(
        self, title: str, body: str, labels: list[str] | None = None
    ) -> IssueResult:
        return IssueResult(number=99, title=title, html_url="", body=body)


# ---------------------------------------------------------------------------
# TS-110-17: Category extraction from issue body
# ---------------------------------------------------------------------------


class TestExtractCategoryFromBody:
    """TS-110-17: extract_category_from_body() extracts the hunt category."""

    def test_extracts_category_field(self) -> None:
        """Category is extracted from '**Category:** dead_code' field."""
        body = "## Title\n\n**Category:** dead_code\n\n**Severity:** minor"
        category = extract_category_from_body(body)
        assert category == "dead_code"

    def test_extracts_different_category(self) -> None:
        """Works for any category value."""
        body = "## Issue\n\n**Category:** linter_debt\n\nDescription."
        assert extract_category_from_body(body) == "linter_debt"

    def test_missing_category_returns_unknown(self) -> None:
        """TS-110-E10: Missing category field returns 'unknown'."""
        body = "No category here at all."
        assert extract_category_from_body(body) == "unknown"

    def test_category_with_trailing_whitespace(self) -> None:
        """Category value is stripped of whitespace."""
        body = "**Category:**   security  \n\nMore content."
        result = extract_category_from_body(body)
        assert result == "security"

    def test_empty_body_returns_unknown(self) -> None:
        """Empty body returns 'unknown'."""
        assert extract_category_from_body("") == "unknown"


# ---------------------------------------------------------------------------
# TS-110-12: Knowledge ingestion creates anti_pattern fact
# ---------------------------------------------------------------------------


class TestIngestCreatesAntiPatternFact:
    """TS-110-12: ingest_ignore_signals() creates an anti_pattern fact."""

    async def test_creates_fact_for_new_issue(
        self, knowledge_conn: object
    ) -> None:
        """One new af:ignore issue → one anti_pattern fact in knowledge store."""
        import duckdb

        conn: duckdb.DuckDBPyConnection = knowledge_conn  # type: ignore[assignment]

        issue = _make_issue(
            number=42,
            title="Dead code: unused_fn",
            category="dead_code",
        )
        platform = _MockPlatform(ignore_issues=[issue])
        embedder = _SameVectorEmbedder()

        count = await ingest_ignore_signals(platform, conn, embedder)  # type: ignore[arg-type]

        assert count == 1

        # Verify fact was created with correct fields
        facts = conn.execute(
            "SELECT category, spec_name, confidence, content "
            "FROM memory_facts "
            "WHERE spec_name = 'nightshift:ignore'"
        ).fetchall()
        assert len(facts) == 1
        fact_category, fact_spec_name, fact_confidence, fact_content = facts[0]
        assert fact_category == "anti_pattern"
        assert fact_spec_name == "nightshift:ignore"
        assert fact_confidence == pytest.approx(0.9)
        assert "unused_fn" in fact_content

    async def test_returns_zero_for_no_issues(
        self, knowledge_conn: object
    ) -> None:
        """No af:ignore issues → returns 0."""
        platform = _MockPlatform(ignore_issues=[])
        embedder = _SameVectorEmbedder()

        count = await ingest_ignore_signals(platform, knowledge_conn, embedder)  # type: ignore[arg-type]

        assert count == 0


# ---------------------------------------------------------------------------
# TS-110-13: Knowledge ingestion appends marker
# ---------------------------------------------------------------------------


class TestIngestAppendsMarker:
    """TS-110-13: ingest_ignore_signals() appends the knowledge-ingested marker."""

    async def test_appends_marker_to_issue_body(
        self, knowledge_conn: object
    ) -> None:
        """After ingestion, update_issue is called with body ending in marker."""
        issue = _make_issue(number=7, title="Security issue", category="security")
        platform = _MockPlatform(ignore_issues=[issue])
        embedder = _SameVectorEmbedder()

        await ingest_ignore_signals(platform, knowledge_conn, embedder)  # type: ignore[arg-type]

        # update_issue must have been called for issue number 7
        assert len(platform.update_issue_calls) == 1
        call = platform.update_issue_calls[0]
        assert call["number"] == 7
        assert str(call["body"]).endswith(_KNOWLEDGE_INGESTED_MARKER)

    async def test_appended_body_contains_original_content(
        self, knowledge_conn: object
    ) -> None:
        """Original body content is preserved when marker is appended."""
        original_body = (
            "## Security issue\n\n**Category:** security\n\nUser-written content."
        )
        issue = _make_issue(number=8, title="Security issue", body=original_body)
        platform = _MockPlatform(ignore_issues=[issue])
        embedder = _SameVectorEmbedder()

        await ingest_ignore_signals(platform, knowledge_conn, embedder)  # type: ignore[arg-type]

        call = platform.update_issue_calls[0]
        updated_body = str(call["body"])
        assert "User-written content." in updated_body
        assert _KNOWLEDGE_INGESTED_MARKER in updated_body


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestMarkerAlreadyPresent:
    """TS-110-E5: Issue with existing marker is skipped."""

    async def test_ingested_issue_skipped(self, knowledge_conn: object) -> None:
        """Issue already containing marker → count=0, no new fact."""
        issue = _make_issue(number=1, with_marker=True)
        platform = _MockPlatform(ignore_issues=[issue])
        embedder = _SameVectorEmbedder()

        count = await ingest_ignore_signals(platform, knowledge_conn, embedder)  # type: ignore[arg-type]

        assert count == 0
        # No update needed for already-ingested issue
        assert len(platform.update_issue_calls) == 0

    async def test_ingested_issue_produces_no_fact(self, knowledge_conn: object) -> None:
        """Already-ingested issue creates no fact in knowledge store."""
        import duckdb

        conn: duckdb.DuckDBPyConnection = knowledge_conn  # type: ignore[assignment]

        issue = _make_issue(number=1, with_marker=True)
        platform = _MockPlatform(ignore_issues=[issue])
        embedder = _SameVectorEmbedder()

        await ingest_ignore_signals(platform, conn, embedder)  # type: ignore[arg-type]

        facts = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE spec_name = 'nightshift:ignore'"
        ).fetchone()
        assert facts is not None
        assert facts[0] == 0


class TestUpdateIssueFailure:
    """TS-110-E6: update_issue failure still creates the fact."""

    async def test_fact_created_despite_update_failure(
        self, knowledge_conn: object
    ) -> None:
        """When update_issue raises, fact is still persisted and count=1."""
        import duckdb

        conn: duckdb.DuckDBPyConnection = knowledge_conn  # type: ignore[assignment]

        issue = _make_issue(number=3, title="Linter debt: unused import")
        platform = _MockPlatform(ignore_issues=[issue], update_raises=True)
        embedder = _SameVectorEmbedder()

        count = await ingest_ignore_signals(platform, conn, embedder)  # type: ignore[arg-type]

        # Fact is still created
        assert count == 1
        facts = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE spec_name = 'nightshift:ignore'"
        ).fetchone()
        assert facts is not None
        assert facts[0] == 1


class TestKnowledgeStoreUnavailable:
    """TS-110-E7: When DuckDB connection is None, ingestion is skipped."""

    async def test_none_conn_returns_zero(self) -> None:
        """conn=None → returns 0, no error."""
        issue = _make_issue(number=1)
        platform = _MockPlatform(ignore_issues=[issue])
        embedder = _SameVectorEmbedder()

        count = await ingest_ignore_signals(platform, None, embedder)  # type: ignore[arg-type]

        assert count == 0


# ---------------------------------------------------------------------------
# TS-110-P6: Ingestion Idempotency (property test)
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestIngestionIdempotency:
    """TS-110-P6: Double ingestion produces exactly one fact."""

    @given(
        title=st.text(
            alphabet=st.characters(whitelist_categories=["L", "N", "P"]),
            min_size=3,
            max_size=40,
        )
    )
    @settings(max_examples=10)
    def test_second_ingest_returns_zero(self, title: str) -> None:
        """Calling ingest twice: first returns 1, second returns 0."""
        import duckdb

        from tests.unit.knowledge.conftest import SCHEMA_DDL  # type: ignore[import]

        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)

        issue = _make_issue(title=title)
        embedder = _SameVectorEmbedder()

        loop = asyncio.new_event_loop()
        try:
            # First call: ingests the issue
            platform1 = _MockPlatform(ignore_issues=[issue])
            count1 = loop.run_until_complete(
                ingest_ignore_signals(platform1, conn, embedder)  # type: ignore[arg-type]
            )

            # Second call: the update_issue was called once, simulating that the
            # platform now returns the issue WITH the marker
            issue_with_marker = _make_issue(title=title, with_marker=True)
            platform2 = _MockPlatform(ignore_issues=[issue_with_marker])
            count2 = loop.run_until_complete(
                ingest_ignore_signals(platform2, conn, embedder)  # type: ignore[arg-type]
            )
        finally:
            loop.close()
            conn.close()

        assert count1 == 1
        assert count2 == 0


# ---------------------------------------------------------------------------
# TS-110-SMOKE-2: Full knowledge ingestion path
# ---------------------------------------------------------------------------


class TestIngestionSmoke:
    """TS-110-SMOKE-2: Full ingestion pipeline exercises real components."""

    async def test_ingests_new_ignores_skips_ingested(
        self, knowledge_conn: object
    ) -> None:
        """One new + one already-ingested → count=1, one update, one fact."""
        import duckdb

        conn: duckdb.DuckDBPyConnection = knowledge_conn  # type: ignore[assignment]

        issue_new = _make_issue(number=10, title="New ignore: dead_code fn")
        issue_old = _make_issue(
            number=11, title="Old ignore: already done", with_marker=True
        )

        platform = _MockPlatform(ignore_issues=[issue_new, issue_old])
        embedder = _SameVectorEmbedder()

        count = await ingest_ignore_signals(platform, conn, embedder)  # type: ignore[arg-type]

        assert count == 1
        # Only the new issue should trigger update_issue
        assert len(platform.update_issue_calls) == 1
        assert platform.update_issue_calls[0]["number"] == 10

        # Exactly one fact should exist in the knowledge store
        facts = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE spec_name = 'nightshift:ignore'"
        ).fetchone()
        assert facts is not None
        assert facts[0] == 1
