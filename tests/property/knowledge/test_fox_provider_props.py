"""Property tests for FoxKnowledgeProvider correctness invariants.

Test Spec: TS-115-P1 through TS-115-P9
Requirements: 115-REQ-1.1, 115-REQ-1.2, 115-REQ-2.4, 115-REQ-2.5,
              115-REQ-2.E1, 115-REQ-2.E3, 115-REQ-3.2, 115-REQ-4.3,
              115-REQ-6.1, 115-REQ-6.2, 115-REQ-6.3, 115-REQ-6.E2,
              115-REQ-7.1
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.gotcha_extraction import GotchaCandidate, extract_gotchas
from agent_fox.knowledge.gotcha_store import compute_content_hash, query_gotchas, store_gotchas
from agent_fox.knowledge.migrations import apply_pending_migrations
from tests.unit.knowledge.conftest import SCHEMA_DDL

# ---------------------------------------------------------------------------
# DDL for spec 115 tables
# ---------------------------------------------------------------------------

_SPEC_115_DDL = """
CREATE TABLE IF NOT EXISTS gotchas (
    id           VARCHAR PRIMARY KEY,
    spec_name    VARCHAR NOT NULL,
    category     VARCHAR NOT NULL DEFAULT 'gotcha',
    text         VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    session_id   VARCHAR NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS errata_index (
    spec_name  VARCHAR NOT NULL,
    file_path  VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (spec_name, file_path)
);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_conn() -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DuckDB with full schema."""
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL)
    apply_pending_migrations(conn)
    conn.execute(_SPEC_115_DDL)
    return conn


def _make_provider_db(conn):
    from agent_fox.knowledge.db import KnowledgeDB

    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = conn
    return db


def _make_candidate(text: str) -> GotchaCandidate:
    content_hash = compute_content_hash(text)
    return GotchaCandidate(text=text, content_hash=content_hash)


def _insert_gotcha_raw(conn, spec_name, text, *, days_ago=0):
    normalized = " ".join(text.lower().split())
    content_hash = hashlib.sha256(normalized.encode()).hexdigest()
    created_at = datetime.now(UTC) - timedelta(days=days_ago)
    conn.execute(
        "INSERT INTO gotchas (id, spec_name, category, text, content_hash, "
        "session_id, created_at) VALUES (?, ?, 'gotcha', ?, ?, ?, ?)",
        [str(uuid.uuid4()), spec_name, text, content_hash, "s1", created_at],
    )


def _insert_review_finding(conn, spec_name, severity, description):
    from agent_fox.knowledge.review_store import ReviewFinding, insert_findings

    finding_id = str(uuid.uuid4())
    finding = ReviewFinding(
        id=finding_id,
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group=finding_id,
        session_id="s1",
    )
    insert_findings(conn, [finding])


def _insert_errata(conn, spec_name, file_path):
    conn.execute(
        "INSERT INTO errata_index (spec_name, file_path, created_at) "
        "VALUES (?, ?, CURRENT_TIMESTAMP)",
        [spec_name, file_path],
    )


# ===========================================================================
# TS-115-P1: Protocol Conformance
# ===========================================================================


class TestProtocolConformance:
    """FoxKnowledgeProvider always satisfies isinstance check.

    Property 1: For any valid KnowledgeDB and KnowledgeProviderConfig,
    isinstance(FoxKnowledgeProvider(db, config), KnowledgeProvider) is True.

    Requirements: 115-REQ-1.1, 115-REQ-1.2
    """

    @given(st.just(True))
    @settings(max_examples=5)
    def test_protocol_conformance(self, _: bool) -> None:
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.provider import KnowledgeProvider

        conn = _fresh_conn()
        db = _make_provider_db(conn)
        provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())
        assert isinstance(provider, KnowledgeProvider)
        conn.close()


# ===========================================================================
# TS-115-P2: Gotcha Deduplication
# ===========================================================================


class TestGotchaDeduplication:
    """Duplicate content hashes for same spec are stored only once.

    Property 2: After storing all candidates, count of rows for spec
    equals count of unique content hashes.

    Requirements: 115-REQ-2.4, 115-REQ-2.E1
    """

    @given(texts=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=10))
    @settings(max_examples=30)
    def test_dedup(self, texts: list[str]) -> None:
        conn = _fresh_conn()
        candidates = [_make_candidate(t) for t in texts]
        store_gotchas(conn, "spec_01", "s1", candidates)

        rows = conn.execute(
            "SELECT * FROM gotchas WHERE spec_name = 'spec_01'"
        ).fetchall()
        expected = len({compute_content_hash(t) for t in texts})
        assert len(rows) == expected
        conn.close()


# ===========================================================================
# TS-115-P3: Gotcha TTL Exclusion
# ===========================================================================


class TestGotchaTTLExclusion:
    """Gotchas older than TTL never appear in retrieval.

    Property 3: A gotcha with age > ttl_days is not in the result.

    Requirements: 115-REQ-3.2, 115-REQ-7.1
    """

    @given(
        ttl=st.integers(min_value=0, max_value=365),
        age=st.integers(min_value=0, max_value=400),
    )
    @settings(max_examples=50)
    def test_ttl_exclusion(self, ttl: int, age: int) -> None:
        conn = _fresh_conn()
        _insert_gotcha_raw(conn, "spec_01", f"Gotcha aged {age}", days_ago=age)

        result = query_gotchas(conn, "spec_01", ttl_days=ttl, limit=5)

        if age > ttl:
            assert len(result) == 0
        conn.close()


# ===========================================================================
# TS-115-P4: Retrieval Cap
# ===========================================================================


class TestRetrievalCap:
    """Total items respect max_items unless reviews+errata exceed it.

    Property 4: len(result) <= max(max_items, n_reviews + n_errata).

    Requirements: 115-REQ-6.1, 115-REQ-6.2, 115-REQ-6.E2
    """

    @given(
        n_gotchas=st.integers(min_value=0, max_value=10),
        n_reviews=st.integers(min_value=0, max_value=10),
        n_errata=st.integers(min_value=0, max_value=5),
        max_items=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=50)
    def test_retrieval_cap(
        self,
        n_gotchas: int,
        n_reviews: int,
        n_errata: int,
        max_items: int,
    ) -> None:
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        from agent_fox.core.config import KnowledgeProviderConfig

        conn = _fresh_conn()
        for i in range(n_gotchas):
            _insert_gotcha_raw(conn, "spec_01", f"Gotcha {i}")
        for i in range(n_reviews):
            _insert_review_finding(conn, "spec_01", "critical", f"Finding {i}")
        for i in range(n_errata):
            _insert_errata(conn, "spec_01", f"docs/errata/e_{i}.md")

        db = _make_provider_db(conn)
        provider = FoxKnowledgeProvider(
            db, KnowledgeProviderConfig(max_items=max_items)
        )
        result = provider.retrieve("spec_01", "task")

        assert len(result) <= max(max_items, n_reviews + n_errata)
        conn.close()


# ===========================================================================
# TS-115-P5: Category Priority Order
# ===========================================================================


class TestCategoryPriorityOrder:
    """Items always appear in errata-review-gotcha order.

    Property 5: All [ERRATA] items precede all [REVIEW] items,
    which precede all [GOTCHA] items.

    Requirements: 115-REQ-6.3
    """

    @given(st.just(True))
    @settings(max_examples=5)
    def test_category_order(self, _: bool) -> None:
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        from agent_fox.core.config import KnowledgeProviderConfig

        conn = _fresh_conn()
        _insert_gotcha_raw(conn, "spec_01", "A gotcha")
        _insert_review_finding(conn, "spec_01", "critical", "A finding")
        _insert_errata(conn, "spec_01", "docs/errata/test.md")

        db = _make_provider_db(conn)
        provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())
        result = provider.retrieve("spec_01", "task")

        categories = [r.split("]")[0] + "]" for r in result]
        seen_review = False
        seen_gotcha = False
        for cat in categories:
            if cat == "[ERRATA]":
                assert not seen_review and not seen_gotcha
            elif cat == "[REVIEW]":
                seen_review = True
                assert not seen_gotcha
            elif cat == "[GOTCHA]":
                seen_gotcha = True
        conn.close()


# ===========================================================================
# TS-115-P6: Gotcha Extraction Cap
# ===========================================================================


class TestGotchaExtractionCap:
    """extract_gotchas always returns at most 3 candidates.

    Property 6: For any LLM response with N candidates where N > 0,
    len(extract_gotchas(...)) <= 3.

    Requirements: 115-REQ-2.E3
    """

    @given(n=st.integers(min_value=0, max_value=20))
    @settings(max_examples=30)
    def test_extraction_cap(self, n: int) -> None:
        mock_candidates = [_make_candidate(f"gotcha_{i}") for i in range(n)]

        with patch(
            "agent_fox.knowledge.gotcha_extraction._call_llm",
            return_value=mock_candidates,
        ):
            context = {
                "session_status": "completed",
                "touched_files": [],
                "commit_sha": "",
            }
            result = extract_gotchas(context, "SIMPLE")
            assert len(result) <= 3


# ===========================================================================
# TS-115-P7: Failed Session Skip
# ===========================================================================


class TestFailedSessionSkip:
    """Non-completed sessions never trigger extraction.

    Property 7: For any non-completed status, ingest() does not call LLM.

    Requirements: 115-REQ-2.5
    """

    @given(
        status=st.sampled_from(["failed", "timeout", "", "in_progress"]),
    )
    @settings(max_examples=10)
    def test_skip_non_completed(self, status: str) -> None:
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        from agent_fox.core.config import KnowledgeProviderConfig

        conn = _fresh_conn()
        db = _make_provider_db(conn)
        provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())

        with patch(
            "agent_fox.knowledge.gotcha_extraction.extract_gotchas",
        ) as mock_extract:
            provider.ingest(
                "s1",
                "spec_01",
                {
                    "session_status": status,
                    "touched_files": [],
                    "commit_sha": "",
                },
            )
            mock_extract.assert_not_called()
        conn.close()


# ===========================================================================
# TS-115-P8: Content Hash Determinism
# ===========================================================================


class TestContentHashDeterminism:
    """Same text always produces the same hash; whitespace/case variations
    produce the same hash.

    Property 8: compute_content_hash(t) == compute_content_hash(t) and
    compute_content_hash(t.upper()) == compute_content_hash(t.lower()).

    Requirements: 115-REQ-2.4
    """

    @given(text=st.text(min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_hash_determinism(self, text: str) -> None:
        h1 = compute_content_hash(text)
        h2 = compute_content_hash(text)
        assert h1 == h2
        assert compute_content_hash(text.upper()) == compute_content_hash(
            text.lower()
        )


# ===========================================================================
# TS-115-P9: Review Category Prefix
# ===========================================================================


class TestReviewCategoryPrefix:
    """Every review finding string has the correct prefix format.

    Property 9: Formatted string starts with "[REVIEW] " and contains
    the severity.

    Requirements: 115-REQ-4.3
    """

    @given(severity=st.sampled_from(["critical", "major"]))
    @settings(max_examples=10)
    def test_review_prefix(self, severity: str) -> None:
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        from agent_fox.core.config import KnowledgeProviderConfig

        conn = _fresh_conn()
        _insert_review_finding(conn, "spec_01", severity, f"A {severity} issue")

        db = _make_provider_db(conn)
        provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())
        result = provider.retrieve("spec_01", "task")

        reviews = [r for r in result if r.startswith("[REVIEW]")]
        for r in reviews:
            assert r.startswith("[REVIEW] ")
            assert severity in r.lower()
        conn.close()
