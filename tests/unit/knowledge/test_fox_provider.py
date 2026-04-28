"""Unit tests for FoxKnowledgeProvider and related configuration/migration.

Test Spec: TS-115-1, TS-115-2, TS-115-3, TS-115-13, TS-115-15,
           TS-115-26, TS-115-27,
           TS-115-32, TS-115-33, TS-115-34,
           TS-115-E1, TS-115-E6, TS-115-E10
Requirements: 115-REQ-1.1, 115-REQ-1.2, 115-REQ-1.3, 115-REQ-1.E1,
              115-REQ-4.1, 115-REQ-4.E1,
              115-REQ-6.E1,
              115-REQ-8.2, 115-REQ-8.3,
              115-REQ-10.1, 115-REQ-10.2, 115-REQ-10.3

Note: Tests for gotchas, errata, and removed config fields (gotcha_ttl_days,
model_tier) were deleted as part of spec 116 (knowledge system pruning).
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.knowledge.migrations import run_migrations
from agent_fox.knowledge.review_store import (
    ReviewFinding,
    insert_findings,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def provider_conn() -> duckdb.DuckDBPyConnection:
    """DuckDB with full migrated schema for provider tests."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture()
def provider_db(provider_conn: duckdb.DuckDBPyConnection):
    """KnowledgeDB wrapper around provider_conn."""
    from agent_fox.knowledge.db import KnowledgeDB

    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = provider_conn
    return db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(provider_db, **overrides):
    """Construct FoxKnowledgeProvider with default or overridden config."""
    from agent_fox.core.config import KnowledgeProviderConfig
    from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

    config = overrides.pop("config", KnowledgeProviderConfig())
    return FoxKnowledgeProvider(provider_db, config)


def _insert_review_finding(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    severity: str,
    description: str,
    *,
    category: str | None = None,
) -> None:
    """Insert a review finding via the existing review_store API.

    Uses a unique task_group per finding to prevent supersession
    between independent findings in the same test.
    """
    finding_id = str(uuid.uuid4())
    finding = ReviewFinding(
        id=finding_id,
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group=finding_id,
        session_id="s1",
        category=category,
    )
    insert_findings(conn, [finding])


# ===========================================================================
# TS-115-1: FoxKnowledgeProvider Implements Protocol
# ===========================================================================


class TestProtocolDefinition:
    """Verify FoxKnowledgeProvider has ingest and retrieve methods.

    Requirements: 115-REQ-1.1
    """

    def test_has_ingest_method(self) -> None:
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        assert hasattr(FoxKnowledgeProvider, "ingest")

    def test_has_retrieve_method(self) -> None:
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        assert hasattr(FoxKnowledgeProvider, "retrieve")


# ===========================================================================
# TS-115-2: FoxKnowledgeProvider isinstance Check
# ===========================================================================


class TestIsinstanceCheck:
    """Verify isinstance(FoxKnowledgeProvider(...), KnowledgeProvider) is True.

    Requirements: 115-REQ-1.2
    """

    def test_isinstance_check(self, provider_db) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
        from agent_fox.knowledge.provider import KnowledgeProvider

        provider = FoxKnowledgeProvider(provider_db, KnowledgeProviderConfig())
        assert isinstance(provider, KnowledgeProvider)


# ===========================================================================
# TS-115-3: Constructor Accepts KnowledgeDB and Config
# ===========================================================================


class TestConstructor:
    """Verify constructor accepts required parameters without error.

    Requirements: 115-REQ-1.3
    """

    def test_constructor_succeeds(self, provider_db) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        provider = FoxKnowledgeProvider(provider_db, KnowledgeProviderConfig())
        assert provider is not None


# ===========================================================================
# TS-115-13: Review Carry-Forward
# ===========================================================================


class TestReviewCarryForward:
    """Verify retrieve() includes unresolved critical/major review findings.

    Requirements: 115-REQ-4.1
    """

    def test_critical_finding_included_minor_excluded(self, provider_db, provider_conn) -> None:
        _insert_review_finding(provider_conn, "spec_01", "critical", "SQL injection vulnerability")
        _insert_review_finding(provider_conn, "spec_01", "minor", "Typo in comment")

        provider = _make_provider(provider_db)
        result = provider.retrieve("spec_01", "task desc")
        reviews = [r for r in result if r.startswith("[REVIEW]")]

        assert len(reviews) == 1
        assert "critical" in reviews[0].lower()


# ===========================================================================
# TS-115-15: Review Finding Prefix
# ===========================================================================


class TestReviewPrefix:
    """Verify review finding strings have [REVIEW] prefix with severity,
    category, and description.

    Requirements: 115-REQ-4.3
    """

    def test_prefix_and_content(self, provider_db, provider_conn) -> None:
        _insert_review_finding(
            provider_conn,
            "spec_01",
            "critical",
            "SQL injection",
            category="security",
        )

        provider = _make_provider(provider_db)
        result = provider.retrieve("spec_01", "task desc")
        reviews = [r for r in result if r.startswith("[REVIEW]")]

        assert len(reviews) == 1
        assert reviews[0].startswith("[REVIEW] ")
        assert "critical" in reviews[0].lower()
        assert "security" in reviews[0].lower()
        assert "SQL injection" in reviews[0]


# ===========================================================================
# TS-115-E1: Closed DB Connection
# ===========================================================================


class TestClosedDB:
    """Verify descriptive error when DB connection is unavailable.

    Requirements: 115-REQ-1.E1

    Note: After spec 116 simplification, a closed DuckDB connection is
    handled gracefully (returns empty list). Setting _conn = None triggers
    the KnowledgeStoreError path via KnowledgeDB.connection property.
    """

    def test_none_conn_raises_knowledge_store_error(self, provider_db) -> None:
        provider = _make_provider(provider_db)
        provider_db._conn = None

        with pytest.raises(KnowledgeStoreError):
            provider.retrieve("spec_01", "task desc")

    def test_closed_conn_returns_empty(self, provider_db) -> None:
        """Closed connection returns empty list (graceful degradation)."""
        provider = _make_provider(provider_db)
        provider_db._conn.close()

        result = provider.retrieve("spec_01", "task desc")
        assert result == []


# ===========================================================================
# TS-115-E6: No Findings for Spec
# ===========================================================================


class TestNoFindings:
    """Verify empty review contribution when no findings exist for the spec.

    Requirements: 115-REQ-4.E1
    """

    def test_no_findings(self, provider_db) -> None:
        provider = _make_provider(provider_db)
        result = provider.retrieve("spec_01", "task desc")
        reviews = [r for r in result if r.startswith("[REVIEW]")]
        assert len(reviews) == 0


# ===========================================================================
# TS-115-E7: Missing review_findings Table
# ===========================================================================


class TestMissingReviewTable:
    """Verify graceful handling when review_findings table is absent.

    Requirements: 115-REQ-4.E2
    """

    def test_missing_review_table(self) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.db import KnowledgeDB
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        # Fresh DB with only schema_version, no review_findings
        conn = duckdb.connect(":memory:")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "  version INTEGER PRIMARY KEY,"
            "  applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "  description TEXT"
            ")"
        )

        db = KnowledgeDB.__new__(KnowledgeDB)
        db._conn = conn

        provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())
        result = provider.retrieve("spec_01", "task desc")
        reviews = [r for r in result if r.startswith("[REVIEW]")]
        assert len(reviews) == 0

        conn.close()


# ===========================================================================
# TS-115-E10: All Categories Empty
# ===========================================================================


class TestAllEmpty:
    """Verify empty list when all categories are empty.

    Requirements: 115-REQ-6.E1
    """

    def test_all_empty(self, provider_db) -> None:
        provider = _make_provider(provider_db)
        result = provider.retrieve("spec_01", "task desc")
        assert result == []


# ===========================================================================
# TS-115-26: Config Nested in KnowledgeConfig
# ===========================================================================


class TestConfigNested:
    """Verify KnowledgeProviderConfig is a field in KnowledgeConfig.

    Requirements: 115-REQ-8.2
    """

    def test_provider_field_in_knowledge_config(self) -> None:
        from agent_fox.core.config import KnowledgeConfig

        assert "provider" in KnowledgeConfig.model_fields
        kc = KnowledgeConfig()
        assert kc.provider.max_items == 10


# ===========================================================================
# TS-115-27: Config Extra Ignore
# ===========================================================================


class TestConfigExtraIgnore:
    """Verify KnowledgeProviderConfig ignores unknown fields.

    Requirements: 115-REQ-8.3
    """

    def test_unknown_fields_ignored(self) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig

        cfg = KnowledgeProviderConfig(max_items=5, unknown_field="foo")
        assert cfg.max_items == 5
        assert not hasattr(cfg, "unknown_field")


# ===========================================================================
# TS-115-32: Provider Construction at Startup
# ===========================================================================


class TestStartupConstruction:
    """Verify _setup_infrastructure constructs FoxKnowledgeProvider.

    Requirements: 115-REQ-10.1
    """

    def test_infra_contains_fox_provider(self) -> None:
        from agent_fox.engine.run import _setup_infrastructure
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        with (
            patch("agent_fox.engine.run.open_knowledge_store") as mock_store,
            patch("agent_fox.engine.run.DuckDBSink"),
            patch("agent_fox.engine.run.SinkDispatcher") as mock_sink_cls,
            patch("agent_fox.knowledge.agent_trace.AgentTraceSink"),
        ):
            mock_db = MagicMock()
            mock_db.connection = MagicMock()
            mock_store.return_value = mock_db
            mock_sink_cls.return_value = MagicMock()

            mock_config = MagicMock()
            mock_config.knowledge = MagicMock()

            infra = _setup_infrastructure(mock_config)

        assert "knowledge_provider" in infra
        assert isinstance(infra["knowledge_provider"], FoxKnowledgeProvider)


# ===========================================================================
# TS-115-33: Replaces NoOpKnowledgeProvider
# ===========================================================================


class TestReplacesNoop:
    """Verify FoxKnowledgeProvider replaces NoOpKnowledgeProvider as default.

    Requirements: 115-REQ-10.2
    """

    def test_not_noop(self) -> None:
        from agent_fox.engine.run import _setup_infrastructure
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
        from agent_fox.knowledge.provider import NoOpKnowledgeProvider

        with (
            patch("agent_fox.engine.run.open_knowledge_store") as mock_store,
            patch("agent_fox.engine.run.DuckDBSink"),
            patch("agent_fox.engine.run.SinkDispatcher") as mock_sink_cls,
            patch("agent_fox.knowledge.agent_trace.AgentTraceSink"),
        ):
            mock_db = MagicMock()
            mock_db.connection = MagicMock()
            mock_store.return_value = mock_db
            mock_sink_cls.return_value = MagicMock()

            mock_config = MagicMock()
            mock_config.knowledge = MagicMock()

            infra = _setup_infrastructure(mock_config)

        assert not isinstance(infra["knowledge_provider"], NoOpKnowledgeProvider)
        assert isinstance(infra["knowledge_provider"], FoxKnowledgeProvider)


# ===========================================================================
# TS-115-34: Engine Import Boundary
# ===========================================================================


class TestImportBoundary:
    """Verify engine modules only import from the allowed knowledge module set.

    Requirements: 115-REQ-10.3
    """

    def test_engine_import_boundary(self) -> None:
        allowed = {
            "provider",
            "db",
            "review_store",
            "audit",
            "sink",
            "duckdb_sink",
            "agent_trace",
            "migrations",
            "fox_provider",
            "errata",
        }

        # knowledge_harvest.py is the knowledge-engine integration pipeline
        # that predates the boundary requirement (spec 115). It legitimately
        # imports from knowledge internals (extraction, lifecycle, etc.).
        # See docs/errata/115_engine_import_boundary.md.
        excluded = {"knowledge_harvest.py"}

        engine_dir = Path(__file__).parents[3] / "agent_fox" / "engine"
        for py_file in engine_dir.glob("*.py"):
            if py_file.name in excluded:
                continue
            source = py_file.read_text()
            for match in re.findall(r"agent_fox\.knowledge\.(\w+)", source):
                assert match in allowed, (
                    f"{py_file.name} imports agent_fox.knowledge.{match} which is not in the allowed set: {allowed}"
                )


# ===========================================================================
# Issue #553: observation/minor findings must not appear in retrieve() output
# ===========================================================================


class TestReviewCarryForwardExcludesObservation:
    """AC-4: retrieve() returns no [REVIEW] items when only observation/minor
    findings exist for a spec.

    Issue #553: observation findings were previously stored but never retrieved,
    wasting storage. Now they are not stored at all; this test ensures the
    retrieval layer also rejects any legacy observation rows.
    """

    def test_observation_finding_excluded(self, provider_db, provider_conn) -> None:
        """retrieve() returns no [REVIEW] items for a spec with only observation findings."""
        # Insert observation finding directly via SQL to simulate legacy data
        # (insert_findings now drops these, so we bypass it).
        provider_conn.execute(
            "INSERT INTO review_findings "
            "(id, severity, description, spec_name, task_group, session_id, created_at) "
            "VALUES (gen_random_uuid(), 'observation', 'Observation note', "
            "'spec_01', 'tg1', 's1', CURRENT_TIMESTAMP)"
        )

        provider = _make_provider(provider_db)
        result = provider.retrieve("spec_01", "task")
        reviews = [r for r in result if r.startswith("[REVIEW]")]
        assert reviews == [], (
            f"Expected no [REVIEW] items for observation-only spec, got: {reviews}"
        )

    def test_minor_finding_excluded(self, provider_db, provider_conn) -> None:
        """retrieve() returns no [REVIEW] items for a spec with only minor findings."""
        provider_conn.execute(
            "INSERT INTO review_findings "
            "(id, severity, description, spec_name, task_group, session_id, created_at) "
            "VALUES (gen_random_uuid(), 'minor', 'Minor style nit', "
            "'spec_02', 'tg1', 's1', CURRENT_TIMESTAMP)"
        )

        provider = _make_provider(provider_db)
        result = provider.retrieve("spec_02", "task")
        reviews = [r for r in result if r.startswith("[REVIEW]")]
        assert reviews == [], (
            f"Expected no [REVIEW] items for minor-only spec, got: {reviews}"
        )


# ===========================================================================
# AC-1 (issue #556): retrieve() filters findings by task_group when provided
# ===========================================================================


class TestTaskGroupFiltering:
    """AC-1 & AC-5: retrieve() filters by task_group when provided; returns
    all groups when task_group is None.

    Issue #556: the knowledge pipeline injected all findings for a spec into
    every coder session regardless of relevance.  Wiring task_group through
    retrieve() → _query_reviews() → query_active_findings() fixes this.
    """

    def _insert_finding_for_group(
        self,
        conn: duckdb.DuckDBPyConnection,
        spec_name: str,
        task_group: str,
        description: str,
    ) -> None:
        """Insert a critical finding tagged to a specific task_group."""
        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description=description,
            requirement_ref=None,
            spec_name=spec_name,
            task_group=task_group,
            session_id="sess-setup",
        )
        insert_findings(conn, [finding])

    def test_ac1_filter_by_task_group_excludes_other_groups(
        self, provider_db, provider_conn
    ) -> None:
        """AC-1: retrieve(task_group='tg1') returns only tg1 findings.

        tg2 finding must be absent from the result.
        """
        self._insert_finding_for_group(provider_conn, "spec_01", "tg1", "tg1-description")
        self._insert_finding_for_group(provider_conn, "spec_01", "tg2", "tg2-description")

        provider = _make_provider(provider_db)
        result = provider.retrieve("spec_01", "desc", task_group="tg1")
        reviews = [r for r in result if r.startswith("[REVIEW]")]

        assert len(reviews) == 1, f"Expected 1 review, got {len(reviews)}: {reviews}"
        assert "tg2-description" not in "\n".join(reviews), (
            "tg2 finding should not appear when task_group='tg1'"
        )
        assert "tg1-description" in reviews[0]

    def test_ac5_no_task_group_returns_all_groups(
        self, provider_db, provider_conn
    ) -> None:
        """AC-5: retrieve() without task_group returns findings from all groups.

        Backward-compatible: omitting task_group means no filtering.
        """
        self._insert_finding_for_group(provider_conn, "spec_01", "tg1", "tg1-description")
        self._insert_finding_for_group(provider_conn, "spec_01", "tg2", "tg2-description")

        provider = _make_provider(provider_db)
        result = provider.retrieve("spec_01", "desc")
        reviews = [r for r in result if r.startswith("[REVIEW]")]

        assert len(reviews) == 2, f"Expected 2 reviews without task_group, got {len(reviews)}: {reviews}"
        descriptions = "\n".join(reviews)
        assert "tg1-description" in descriptions
        assert "tg2-description" in descriptions
