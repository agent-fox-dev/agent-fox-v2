"""Unit tests for pre-review (group 0) finding elevation.

Tests verify that group 0 findings appear in primary review results for
non-zero task groups, are tracked in finding_injections, and are excluded
from cross-group results to avoid duplication.

Test Spec: TS-120-5, TS-120-6, TS-120-7, TS-120-E3, TS-120-E4
Requirements: 120-REQ-2.1, 120-REQ-2.2, 120-REQ-2.3, 120-REQ-2.4,
              120-REQ-2.E1, 120-REQ-2.E2
"""

from __future__ import annotations

import uuid

import duckdb
import pytest

from agent_fox.core.config import KnowledgeProviderConfig
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
from agent_fox.knowledge.migrations import run_migrations
from agent_fox.knowledge.review_store import ReviewFinding

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def provider_conn() -> duckdb.DuckDBPyConnection:
    """DuckDB with full migrated schema."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture()
def provider_db(provider_conn: duckdb.DuckDBPyConnection) -> KnowledgeDB:
    """KnowledgeDB wrapper around provider_conn."""
    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = provider_conn
    return db


def _make_provider(provider_db: KnowledgeDB) -> FoxKnowledgeProvider:
    """Construct FoxKnowledgeProvider with default config."""
    return FoxKnowledgeProvider(provider_db, KnowledgeProviderConfig())


def _make_finding(
    *,
    finding_id: str | None = None,
    spec_name: str = "test_spec",
    task_group: str = "1",
    severity: str = "critical",
    description: str = "Test issue",
    session_id: str = "s1",
    category: str | None = None,
) -> ReviewFinding:
    return ReviewFinding(
        id=finding_id or str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group=task_group,
        session_id=session_id,
        category=category,
    )


def _insert_finding(conn: duckdb.DuckDBPyConnection, finding: ReviewFinding) -> None:
    """Insert a single finding directly (bypasses supersession for test isolation)."""
    conn.execute(
        "INSERT INTO review_findings "
        "(id, severity, description, requirement_ref, spec_name, task_group, session_id, category, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        [
            finding.id,
            finding.severity,
            finding.description,
            finding.requirement_ref,
            finding.spec_name,
            finding.task_group,
            finding.session_id,
            finding.category,
        ],
    )


# ---------------------------------------------------------------------------
# TS-120-5: Pre-review findings in primary review results (120-REQ-2.1, 120-REQ-2.4)
# ---------------------------------------------------------------------------


class TestPreReviewInPrimaryReview:
    """Verify group 0 findings appear in primary review results for non-zero task groups."""

    def test_both_group0_and_same_group_in_review(
        self,
        provider_db: KnowledgeDB,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        _insert_finding(
            provider_conn,
            _make_finding(
                spec_name="test_spec",
                task_group="0",
                severity="critical",
                description="Design issue A",
            ),
        )
        _insert_finding(
            provider_conn,
            _make_finding(
                spec_name="test_spec",
                task_group="1",
                severity="major",
                description="Code issue B",
            ),
        )
        provider = _make_provider(provider_db)
        result = provider.retrieve("test_spec", "test", task_group="1")
        review_items = [i for i in result if i.startswith("[REVIEW]")]
        assert len(review_items) == 2
        assert any("Design issue A" in i for i in review_items)
        assert any("Code issue B" in i for i in review_items)


# ---------------------------------------------------------------------------
# TS-120-6: Pre-review findings tracked in finding_injections (120-REQ-2.2)
# ---------------------------------------------------------------------------


class TestPreReviewFindingsTracked:
    """Verify group 0 findings are recorded in finding_injections."""

    def test_group0_finding_tracked(
        self,
        provider_db: KnowledgeDB,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        finding_id = "F-001"
        _insert_finding(
            provider_conn,
            _make_finding(
                finding_id=finding_id,
                spec_name="test_spec",
                task_group="0",
                severity="critical",
                description="Pre-review issue X",
            ),
        )
        provider = _make_provider(provider_db)
        provider.retrieve("test_spec", "test", task_group="1", session_id="sess-1")

        rows = provider_conn.execute(
            "SELECT * FROM finding_injections WHERE finding_id = ?", [finding_id]
        ).fetchall()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# TS-120-7: Pre-review findings excluded from cross-group (120-REQ-2.3)
# ---------------------------------------------------------------------------


class TestPreReviewExcludedFromCrossGroup:
    """Verify group 0 findings do not appear in cross-group results."""

    def test_group0_not_in_cross_group(
        self,
        provider_db: KnowledgeDB,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        _insert_finding(
            provider_conn,
            _make_finding(
                spec_name="test_spec",
                task_group="0",
                severity="critical",
                description="Pre-review issue",
            ),
        )
        _insert_finding(
            provider_conn,
            _make_finding(
                spec_name="test_spec",
                task_group="2",
                severity="major",
                description="Group 2 issue",
            ),
        )
        provider = _make_provider(provider_db)
        result = provider.retrieve("test_spec", "test", task_group="1")
        cross_group = [i for i in result if "[CROSS-GROUP]" in i]
        assert any("Group 2 issue" in i for i in cross_group)
        assert not any("Pre-review issue" in i for i in cross_group)


# ---------------------------------------------------------------------------
# TS-120-E3: No group 0 findings (120-REQ-2.E1)
# ---------------------------------------------------------------------------


class TestNoGroup0Findings:
    """When no pre-review findings exist, only same-group findings returned."""

    def test_only_same_group_findings(
        self,
        provider_db: KnowledgeDB,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        _insert_finding(
            provider_conn,
            _make_finding(
                spec_name="test_spec",
                task_group="1",
                severity="major",
                description="Code issue",
            ),
        )
        provider = _make_provider(provider_db)
        result = provider.retrieve("test_spec", "test", task_group="1")
        review_items = [i for i in result if i.startswith("[REVIEW]")]
        assert len(review_items) == 1
        assert "Code issue" in review_items[0]


# ---------------------------------------------------------------------------
# TS-120-E4: Group 0 session does not self-inject (120-REQ-2.E2)
# ---------------------------------------------------------------------------


class TestGroup0NoSelfInject:
    """Pre-review session (task_group="0") does not see its own findings in cross-group."""

    def test_no_self_injection(
        self,
        provider_db: KnowledgeDB,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        _insert_finding(
            provider_conn,
            _make_finding(
                spec_name="test_spec",
                task_group="0",
                severity="critical",
                description="My own finding",
            ),
        )
        provider = _make_provider(provider_db)
        result = provider.retrieve("test_spec", "test", task_group="0")
        cross_group = [i for i in result if "[CROSS-GROUP]" in i]
        assert not any("My own finding" in i for i in cross_group)
