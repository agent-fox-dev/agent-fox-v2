"""Unit tests for FoxKnowledgeProvider and related configuration/migration.

Test Spec: TS-115-1, TS-115-2, TS-115-3, TS-115-13, TS-115-14, TS-115-15,
           TS-115-20, TS-115-21, TS-115-22, TS-115-25, TS-115-26, TS-115-27,
           TS-115-28, TS-115-29, TS-115-30, TS-115-31, TS-115-32, TS-115-33,
           TS-115-34, TS-115-E1, TS-115-E5, TS-115-E6, TS-115-E7, TS-115-E8,
           TS-115-E9, TS-115-E10, TS-115-E11, TS-115-E12
Requirements: 115-REQ-1.1, 115-REQ-1.2, 115-REQ-1.3, 115-REQ-1.E1,
              115-REQ-4.1, 115-REQ-4.2, 115-REQ-4.3, 115-REQ-4.E1, 115-REQ-4.E2,
              115-REQ-5.E1, 115-REQ-5.E2,
              115-REQ-6.1, 115-REQ-6.2, 115-REQ-6.3, 115-REQ-6.E1, 115-REQ-6.E2,
              115-REQ-7.E1, 115-REQ-8.1, 115-REQ-8.2, 115-REQ-8.3,
              115-REQ-9.1, 115-REQ-9.2, 115-REQ-9.3, 115-REQ-9.4,
              115-REQ-10.1, 115-REQ-10.2, 115-REQ-10.3
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.knowledge.migrations import apply_pending_migrations
from agent_fox.knowledge.review_store import ReviewFinding, insert_findings
from tests.unit.knowledge.conftest import SCHEMA_DDL

# ---------------------------------------------------------------------------
# DDL for spec 115 tables (matches migration v17 design)
# Used by fixtures for provider-level tests that need seeded data.
# ---------------------------------------------------------------------------

_GOTCHAS_DDL = """
CREATE TABLE IF NOT EXISTS gotchas (
    id           VARCHAR PRIMARY KEY,
    spec_name    VARCHAR NOT NULL,
    category     VARCHAR NOT NULL DEFAULT 'gotcha',
    text         VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    session_id   VARCHAR NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

_ERRATA_INDEX_DDL = """
CREATE TABLE IF NOT EXISTS errata_index (
    spec_name  VARCHAR NOT NULL,
    file_path  VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (spec_name, file_path)
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def provider_conn() -> duckdb.DuckDBPyConnection:
    """DuckDB with full schema + gotchas/errata_index tables for provider tests."""
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL)
    apply_pending_migrations(conn)
    conn.execute(_GOTCHAS_DDL)
    conn.execute(_ERRATA_INDEX_DDL)
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
    from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

    from agent_fox.core.config import KnowledgeProviderConfig

    config = overrides.pop("config", KnowledgeProviderConfig())
    return FoxKnowledgeProvider(provider_db, config)


def _insert_gotcha(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    text: str,
    *,
    days_ago: int = 0,
    session_id: str = "s1",
) -> None:
    """Insert a gotcha directly into the DB for test setup."""
    normalized = " ".join(text.lower().split())
    content_hash = hashlib.sha256(normalized.encode()).hexdigest()
    created_at = datetime.now(UTC) - timedelta(days=days_ago)
    conn.execute(
        "INSERT INTO gotchas (id, spec_name, category, text, content_hash, "
        "session_id, created_at) VALUES (?, ?, 'gotcha', ?, ?, ?, ?)",
        [str(uuid.uuid4()), spec_name, text, content_hash, session_id, created_at],
    )


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


def _insert_errata(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    file_path: str,
) -> None:
    """Insert an errata entry directly into the DB for test setup."""
    conn.execute(
        "INSERT INTO errata_index (spec_name, file_path, created_at) "
        "VALUES (?, ?, CURRENT_TIMESTAMP)",
        [spec_name, file_path],
    )


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
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
        from agent_fox.knowledge.provider import KnowledgeProvider

        from agent_fox.core.config import KnowledgeProviderConfig

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
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        from agent_fox.core.config import KnowledgeProviderConfig

        provider = FoxKnowledgeProvider(provider_db, KnowledgeProviderConfig())
        assert provider is not None


# ===========================================================================
# TS-115-13: Review Carry-Forward
# ===========================================================================


class TestReviewCarryForward:
    """Verify retrieve() includes unresolved critical/major review findings.

    Requirements: 115-REQ-4.1
    """

    def test_critical_finding_included_minor_excluded(
        self, provider_db, provider_conn
    ) -> None:
        _insert_review_finding(
            provider_conn, "spec_01", "critical", "SQL injection vulnerability"
        )
        _insert_review_finding(
            provider_conn, "spec_01", "minor", "Typo in comment"
        )

        provider = _make_provider(provider_db)
        result = provider.retrieve("spec_01", "task desc")
        reviews = [r for r in result if r.startswith("[REVIEW]")]

        assert len(reviews) == 1
        assert "critical" in reviews[0].lower()


# ===========================================================================
# TS-115-14: Review Findings Not Subject to Gotcha Limit
# ===========================================================================


class TestReviewNotLimited:
    """Verify all review findings are included regardless of gotcha limit.

    Requirements: 115-REQ-4.2
    """

    def test_all_reviews_included(self, provider_db, provider_conn) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig

        for i in range(5):
            _insert_gotcha(provider_conn, "spec_01", f"Gotcha {i}")
        for i in range(3):
            _insert_review_finding(
                provider_conn, "spec_01", "critical", f"Critical finding {i}"
            )

        provider = _make_provider(
            provider_db, config=KnowledgeProviderConfig(max_items=10)
        )
        result = provider.retrieve("spec_01", "task desc")
        reviews = [r for r in result if r.startswith("[REVIEW]")]

        assert len(reviews) == 3
        assert len(result) <= 10


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
        assert "SQL injection" in reviews[0]


# ===========================================================================
# TS-115-20: Total Retrieval Cap
# ===========================================================================


class TestTotalCap:
    """Verify total items do not exceed max_items.

    Requirements: 115-REQ-6.1
    """

    def test_total_within_cap(self, provider_db, provider_conn) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig

        for i in range(5):
            _insert_gotcha(provider_conn, "spec_01", f"Gotcha {i}")
        for i in range(3):
            _insert_review_finding(
                provider_conn, "spec_01", "critical", f"Finding {i}"
            )
        for i in range(2):
            _insert_errata(
                provider_conn, "spec_01", f"docs/errata/errata_{i}.md"
            )

        provider = _make_provider(
            provider_db, config=KnowledgeProviderConfig(max_items=10)
        )
        result = provider.retrieve("spec_01", "task desc")

        assert len(result) <= 10


# ===========================================================================
# TS-115-21: Gotchas Trimmed First
# ===========================================================================


class TestGotchasTrimmed:
    """Verify gotchas are trimmed when total exceeds cap.

    Requirements: 115-REQ-6.2
    """

    def test_gotchas_trimmed_first(self, provider_db, provider_conn) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig

        for i in range(5):
            _insert_gotcha(provider_conn, "spec_01", f"Gotcha {i}")
        for i in range(4):
            _insert_review_finding(
                provider_conn, "spec_01", "critical", f"Finding {i}"
            )
        for i in range(3):
            _insert_errata(
                provider_conn, "spec_01", f"docs/errata/errata_{i}.md"
            )

        provider = _make_provider(
            provider_db, config=KnowledgeProviderConfig(max_items=10)
        )
        result = provider.retrieve("spec_01", "task desc")

        reviews = [r for r in result if r.startswith("[REVIEW]")]
        errata = [r for r in result if r.startswith("[ERRATA]")]
        gotchas = [r for r in result if r.startswith("[GOTCHA]")]

        assert len(reviews) == 4
        assert len(errata) == 3
        assert len(gotchas) == 3  # 10 - 4 - 3 = 3
        assert len(result) == 10


# ===========================================================================
# TS-115-22: Category Order
# ===========================================================================


class TestCategoryOrder:
    """Verify retrieval order: errata first, reviews second, gotchas last.

    Requirements: 115-REQ-6.3
    """

    def test_category_order(self, provider_db, provider_conn) -> None:
        _insert_gotcha(provider_conn, "spec_01", "A gotcha")
        _insert_review_finding(
            provider_conn, "spec_01", "critical", "A finding"
        )
        _insert_errata(provider_conn, "spec_01", "docs/errata/01_fix.md")

        provider = _make_provider(provider_db)
        result = provider.retrieve("spec_01", "task desc")

        assert len(result) == 3
        assert result[0].startswith("[ERRATA]")
        assert result[1].startswith("[REVIEW]")
        assert result[2].startswith("[GOTCHA]")


# ===========================================================================
# TS-115-E1: Closed DB Connection
# ===========================================================================


class TestClosedDB:
    """Verify descriptive error when DB connection is closed.

    Requirements: 115-REQ-1.E1
    """

    def test_closed_db_raises_knowledge_store_error(self, provider_db) -> None:
        provider = _make_provider(provider_db)
        provider_db._conn.close()

        with pytest.raises(KnowledgeStoreError):
            provider.retrieve("spec_01", "task desc")


# ===========================================================================
# TS-115-E5: No Gotchas for Spec
# ===========================================================================


class TestNoGotchas:
    """Verify empty gotcha contribution when none exist for the spec.

    Requirements: 115-REQ-3.E1
    """

    def test_no_gotchas(self, provider_db) -> None:
        provider = _make_provider(provider_db)
        result = provider.retrieve("spec_01", "task desc")
        gotchas = [r for r in result if r.startswith("[GOTCHA]")]
        assert len(gotchas) == 0


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
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.db import KnowledgeDB

        # Fresh DB with only gotchas and errata_index, no review_findings
        conn = duckdb.connect(":memory:")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "  version INTEGER PRIMARY KEY,"
            "  applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "  description TEXT"
            ")"
        )
        conn.execute(_GOTCHAS_DDL)
        conn.execute(_ERRATA_INDEX_DDL)

        db = KnowledgeDB.__new__(KnowledgeDB)
        db._conn = conn

        provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())
        result = provider.retrieve("spec_01", "task desc")
        reviews = [r for r in result if r.startswith("[REVIEW]")]
        assert len(reviews) == 0

        conn.close()


# ===========================================================================
# TS-115-E8: No Errata for Spec
# ===========================================================================


class TestNoErrata:
    """Verify empty errata contribution when none registered.

    Requirements: 115-REQ-5.E1
    """

    def test_no_errata(self, provider_db) -> None:
        provider = _make_provider(provider_db)
        result = provider.retrieve("spec_01", "task desc")
        errata = [r for r in result if r.startswith("[ERRATA]")]
        assert len(errata) == 0


# ===========================================================================
# TS-115-E9: Errata File Missing on Disk
# ===========================================================================


class TestErrataFileMissing:
    """Verify errata entry returned even when the file doesn't exist on disk.

    Requirements: 115-REQ-5.E2
    """

    def test_missing_file_still_returned(
        self, provider_db, provider_conn
    ) -> None:
        _insert_errata(
            provider_conn, "spec_01", "docs/errata/nonexistent.md"
        )

        provider = _make_provider(provider_db)
        result = provider.retrieve("spec_01", "task desc")
        errata = [r for r in result if r.startswith("[ERRATA]")]

        assert len(errata) == 1
        assert "nonexistent.md" in errata[0]


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
# TS-115-E11: Reviews+Errata Exceed Cap
# ===========================================================================


class TestReviewsErrataExceedCap:
    """Verify all reviews+errata returned even if exceeding max_items.

    Requirements: 115-REQ-6.E2
    """

    def test_reviews_errata_exceed_cap(
        self, provider_db, provider_conn
    ) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig

        for i in range(8):
            _insert_review_finding(
                provider_conn, "spec_01", "critical", f"Finding {i}"
            )
        for i in range(5):
            _insert_errata(
                provider_conn, "spec_01", f"docs/errata/errata_{i}.md"
            )
        for i in range(3):
            _insert_gotcha(provider_conn, "spec_01", f"Gotcha {i}")

        provider = _make_provider(
            provider_db, config=KnowledgeProviderConfig(max_items=10)
        )
        result = provider.retrieve("spec_01", "task desc")

        reviews = [r for r in result if r.startswith("[REVIEW]")]
        errata = [r for r in result if r.startswith("[ERRATA]")]
        gotchas = [r for r in result if r.startswith("[GOTCHA]")]

        assert len(reviews) == 8
        assert len(errata) == 5
        assert len(gotchas) == 0  # No room for gotchas


# ===========================================================================
# TS-115-E12: TTL Zero Excludes All Gotchas
# ===========================================================================


class TestTTLZero:
    """Verify TTL=0 excludes all gotchas from retrieval.

    Requirements: 115-REQ-7.E1
    """

    def test_ttl_zero(self, provider_db, provider_conn) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig

        for i in range(3):
            _insert_gotcha(provider_conn, "spec_01", f"Gotcha {i}")

        provider = _make_provider(
            provider_db, config=KnowledgeProviderConfig(gotcha_ttl_days=0)
        )
        result = provider.retrieve("spec_01", "task desc")
        gotchas = [r for r in result if r.startswith("[GOTCHA]")]

        assert len(gotchas) == 0


# ===========================================================================
# TS-115-25: KnowledgeProviderConfig Fields
# ===========================================================================


class TestConfigFields:
    """Verify KnowledgeProviderConfig has correct fields and defaults.

    Requirements: 115-REQ-8.1
    """

    def test_default_fields(self) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig

        cfg = KnowledgeProviderConfig()
        assert cfg.max_items == 10
        assert cfg.gotcha_ttl_days == 90
        assert cfg.model_tier == "SIMPLE"


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
# TS-115-28: Gotchas Table Schema
# ===========================================================================


class TestGotchasSchema:
    """Verify gotchas table created with correct columns after migration.

    Requirements: 115-REQ-9.1
    """

    def test_gotchas_table_columns(self) -> None:
        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)
        apply_pending_migrations(conn)

        columns = conn.execute("DESCRIBE gotchas").fetchall()
        col_names = {c[0] for c in columns}

        assert col_names == {
            "id",
            "spec_name",
            "category",
            "text",
            "content_hash",
            "session_id",
            "created_at",
        }
        conn.close()


# ===========================================================================
# TS-115-29: Errata Index Table Schema
# ===========================================================================


class TestErrataSchema:
    """Verify errata_index table created with correct columns.

    Requirements: 115-REQ-9.2
    """

    def test_errata_index_table_columns(self) -> None:
        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)
        apply_pending_migrations(conn)

        columns = conn.execute("DESCRIBE errata_index").fetchall()
        col_names = {c[0] for c in columns}

        assert col_names == {"spec_name", "file_path", "created_at"}
        conn.close()


# ===========================================================================
# TS-115-30: Migration Via Framework
# ===========================================================================


class TestMigrationFramework:
    """Verify tables created through the migration framework.

    Requirements: 115-REQ-9.3
    """

    def test_migration_creates_tables(self) -> None:
        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)
        apply_pending_migrations(conn)

        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = {t[0] for t in tables}

        assert "gotchas" in table_names
        assert "errata_index" in table_names
        conn.close()


# ===========================================================================
# TS-115-31: Idempotent Migration
# ===========================================================================


class TestIdempotentMigration:
    """Verify migration can run twice without error.

    Requirements: 115-REQ-9.4
    """

    def test_idempotent(self) -> None:
        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)
        apply_pending_migrations(conn)
        apply_pending_migrations(conn)  # second run should not raise

        # Verify the v17 tables exist after both runs
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = {t[0] for t in tables}
        assert "gotchas" in table_names
        assert "errata_index" in table_names
        conn.close()


# ===========================================================================
# TS-115-32: Provider Construction at Startup
# ===========================================================================


class TestStartupConstruction:
    """Verify _setup_infrastructure constructs FoxKnowledgeProvider.

    Requirements: 115-REQ-10.1
    """

    def test_infra_contains_fox_provider(self) -> None:
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        from agent_fox.engine.run import _setup_infrastructure

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
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
        from agent_fox.knowledge.provider import NoOpKnowledgeProvider

        from agent_fox.engine.run import _setup_infrastructure

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

        assert not isinstance(
            infra["knowledge_provider"], NoOpKnowledgeProvider
        )
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
            "blocking_history",
            "agent_trace",
            "migrations",
            "fox_provider",
        }

        engine_dir = Path(__file__).parents[3] / "agent_fox" / "engine"
        for py_file in engine_dir.glob("*.py"):
            source = py_file.read_text()
            for match in re.findall(
                r"agent_fox\.knowledge\.(\w+)", source
            ):
                assert match in allowed, (
                    f"{py_file.name} imports agent_fox.knowledge.{match} "
                    f"which is not in the allowed set: {allowed}"
                )
