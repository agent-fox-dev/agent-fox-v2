"""Tests for knowledge system pruning (spec 116).

Verifies that removed components are gone, retained components still work,
the database migration drops the correct tables, and the simplified
FoxKnowledgeProvider returns only review findings.

Test Spec: TS-116-1 through TS-116-20, TS-116-E1 through TS-116-E3,
           TS-116-P1 through TS-116-P3, TS-116-SMOKE-1 through TS-116-SMOKE-3
Requirements: 116-REQ-1.1 through 116-REQ-8.3
"""

from __future__ import annotations

import importlib
import inspect
import uuid

import duckdb
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import KnowledgeProviderConfig
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.migrations import (
    MIGRATIONS,
    get_current_version,
    record_version,
    run_migrations,
)
from agent_fox.knowledge.provider import KnowledgeProvider
from agent_fox.knowledge.review_store import (
    ReviewFinding,
    insert_findings,
    query_active_findings,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DROPPED_TABLES = [
    "gotchas",
    "errata_index",
    "blocking_history",
    "sleep_artifacts",
    "memory_facts",
    "memory_embeddings",
    "entity_graph",
    "entity_edges",
    "fact_entities",
    "fact_causes",
]

_RETAINED_TABLES = [
    "review_findings",
    "verification_results",
    "drift_findings",
    "session_outcomes",
    "tool_calls",
    "tool_errors",
    "audit_events",
    "plan_nodes",
    "plan_edges",
    "plan_meta",
    "runs",
    "schema_version",
]


# Base schema DDL that includes tables to be dropped by v18.
# Used only by tests that need to verify intermediate state (v17 → v18).
_PRE_V18_BASE_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

CREATE TABLE IF NOT EXISTS memory_facts (
    id            UUID PRIMARY KEY,
    content       TEXT NOT NULL,
    category      TEXT,
    spec_name     TEXT,
    session_id    TEXT,
    commit_sha    TEXT,
    confidence    DOUBLE DEFAULT 0.6,
    created_at    TIMESTAMP,
    superseded_by UUID,
    keywords      TEXT[] DEFAULT []
);

CREATE TABLE IF NOT EXISTS memory_embeddings (
    id        UUID PRIMARY KEY REFERENCES memory_facts(id),
    embedding FLOAT[384]
);

CREATE TABLE IF NOT EXISTS session_outcomes (
    id            UUID PRIMARY KEY,
    spec_name     TEXT,
    task_group    TEXT,
    node_id       TEXT,
    touched_path  TEXT,
    status        TEXT,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    duration_ms   INTEGER,
    created_at    TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fact_causes (
    cause_id  UUID,
    effect_id UUID,
    PRIMARY KEY (cause_id, effect_id)
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id         UUID PRIMARY KEY,
    session_id TEXT,
    node_id    TEXT,
    tool_name  TEXT,
    called_at  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tool_errors (
    id        UUID PRIMARY KEY,
    session_id TEXT,
    node_id    TEXT,
    tool_name  TEXT,
    failed_at  TIMESTAMP
);

INSERT INTO schema_version (version, description)
    SELECT 1, 'initial schema'
    WHERE NOT EXISTS (SELECT 1 FROM schema_version WHERE version = 1);
"""


def _apply_migrations_up_to(conn: duckdb.DuckDBPyConnection, max_version: int) -> None:
    """Apply all migrations up to and including *max_version*."""
    current = get_current_version(conn)
    for migration in MIGRATIONS:
        if migration.version <= current:
            continue
        if migration.version > max_version:
            break
        migration.apply(conn)
        record_version(conn, migration.version, migration.description)


def _table_exists(conn: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    """Check whether a table exists in the database."""
    result = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name = ?",
        [table_name],
    ).fetchone()
    return result is not None and result[0] > 0


def _count_rows(conn: duckdb.DuckDBPyConnection, table_name: str) -> int:
    """Count rows in a table."""
    result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()  # noqa: S608
    return result[0] if result else 0


def _make_finding(
    *,
    severity: str = "critical",
    description: str = "Test finding",
    spec_name: str = "test_spec",
    task_group: str = "1",
    session_id: str = "session-1",
    category: str | None = None,
) -> ReviewFinding:
    """Create a ReviewFinding with sensible defaults."""
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group=task_group,
        session_id=session_id,
        category=category,
    )


def _make_provider(knowledge_db: KnowledgeDB, **config_overrides):
    """Construct FoxKnowledgeProvider with default or overridden config."""
    from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

    config = KnowledgeProviderConfig(**config_overrides)
    return FoxKnowledgeProvider(knowledge_db, config)


def _create_knowledge_db(conn: duckdb.DuckDBPyConnection) -> KnowledgeDB:
    """Create a KnowledgeDB wrapper around an existing connection."""
    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = conn
    return db


def _fresh_conn_with_migrations() -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DuckDB with all migrations applied."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    return conn


def _snapshot_table_counts(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Snapshot row counts for all tables in the database."""
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    counts = {}
    for (table_name,) in tables:
        try:
            result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()  # noqa: S608
            counts[table_name] = result[0] if result else 0
        except Exception:
            counts[table_name] = -1
    return counts


# ============================================================================
# TS-116-1: Gotcha extraction module removed
# ============================================================================


class TestGotchaExtractionRemoved:
    """TS-116-1: Verify gotcha_extraction module cannot be imported.

    Requirement: 116-REQ-1.1
    """

    def test_gotcha_extraction_removed(self) -> None:
        """Importing agent_fox.knowledge.gotcha_extraction should raise ImportError."""
        with pytest.raises((ImportError, ModuleNotFoundError)):
            importlib.import_module("agent_fox.knowledge.gotcha_extraction")


# ============================================================================
# TS-116-2: Gotcha store module removed
# ============================================================================


class TestGotchaStoreRemoved:
    """TS-116-2: Verify gotcha_store module cannot be imported.

    Requirement: 116-REQ-1.2
    """

    def test_gotcha_store_removed(self) -> None:
        """Importing agent_fox.knowledge.gotcha_store should raise ImportError."""
        with pytest.raises((ImportError, ModuleNotFoundError)):
            importlib.import_module("agent_fox.knowledge.gotcha_store")


# ============================================================================
# TS-116-3: Ingest is a no-op
# ============================================================================


class TestIngestIsNoop:
    """TS-116-3: Verify FoxKnowledgeProvider.ingest() is a no-op.

    Requirement: 116-REQ-1.3
    """

    def test_ingest_is_noop(self, knowledge_db: KnowledgeDB) -> None:
        """Ingest should return None without LLM calls or DB writes."""
        provider = _make_provider(knowledge_db)
        conn = knowledge_db.connection

        tables_before = _snapshot_table_counts(conn)

        result = provider.ingest(
            "session_1",
            "spec_01",
            {
                "session_status": "completed",
                "touched_files": ["src/main.rs"],
                "commit_sha": "abc123",
            },
        )

        tables_after = _snapshot_table_counts(conn)
        assert result is None
        assert tables_before == tables_after


# ============================================================================
# TS-116-4: Retrieve returns no gotchas
# ============================================================================


class TestRetrieveNoGotchas:
    """TS-116-4: Verify retrieve returns no [GOTCHA]-prefixed items.

    Requirement: 116-REQ-1.4
    """

    def test_retrieve_no_gotchas(self, knowledge_db: KnowledgeDB) -> None:
        """Retrieve should not return any [GOTCHA]-prefixed items."""
        provider = _make_provider(knowledge_db)
        result = provider.retrieve("any_spec", "any task")
        assert all(not item.startswith("[GOTCHA]") for item in result)


# ============================================================================
# TS-116-5: Errata store module removed
# ============================================================================


class TestErrataStoreRemoved:
    """TS-116-5: Verify errata_store module cannot be imported.

    Requirement: 116-REQ-2.1
    """

    def test_errata_store_removed(self) -> None:
        """Importing agent_fox.knowledge.errata_store should raise ImportError."""
        with pytest.raises((ImportError, ModuleNotFoundError)):
            importlib.import_module("agent_fox.knowledge.errata_store")


# ============================================================================
# TS-116-6: Retrieve returns no errata
# ============================================================================


class TestRetrieveNoErrata:
    """TS-116-6: Verify retrieve returns no [ERRATA]-prefixed items.

    Requirement: 116-REQ-2.2
    """

    def test_retrieve_no_errata(self, knowledge_db: KnowledgeDB) -> None:
        """Retrieve should not return any [ERRATA]-prefixed items."""
        provider = _make_provider(knowledge_db)
        result = provider.retrieve("any_spec", "any task")
        assert all(not item.startswith("[ERRATA]") for item in result)


# ============================================================================
# TS-116-7: Blocking history module removed
# ============================================================================


class TestBlockingHistoryRemoved:
    """TS-116-7: Verify blocking_history module cannot be imported.

    Requirement: 116-REQ-3.1
    """

    def test_blocking_history_removed(self) -> None:
        """Importing agent_fox.knowledge.blocking_history should raise ImportError."""
        with pytest.raises((ImportError, ModuleNotFoundError)):
            importlib.import_module("agent_fox.knowledge.blocking_history")


# ============================================================================
# TS-116-8: Result handler does not import blocking_history
# ============================================================================


class TestResultHandlerNoBlocking:
    """TS-116-8: Verify result_handler has no blocking_history references.

    Requirement: 116-REQ-3.E1
    """

    def test_result_handler_no_blocking(self) -> None:
        """result_handler.py source should not reference blocking_history."""
        import agent_fox.engine.result_handler as rh

        source = inspect.getsource(rh)
        assert "blocking_history" not in source
        assert "record_blocking_decision" not in source


# ============================================================================
# TS-116-9: Migration v18 drops unused tables
# ============================================================================


class TestMigrationV18DropsTables:
    """TS-116-9: Verify migration v18 drops exactly 10 specified tables.

    Requirements: 116-REQ-4.1, 116-REQ-4.3
    """

    def test_migration_v18_drops_tables(self) -> None:
        """Migration v18 should drop all 10 specified tables."""
        conn = duckdb.connect(":memory:")
        # Use the pre-v18 base schema which includes dropped tables
        conn.execute(_PRE_V18_BASE_SCHEMA_DDL)
        _apply_migrations_up_to(conn, 17)

        # Verify intermediate state: all dropped tables exist at v17
        current_version = get_current_version(conn)
        assert current_version == 17
        for table in _DROPPED_TABLES:
            assert _table_exists(conn, table), f"Table {table} should exist at v17"

        # Apply v18
        _apply_migrations_up_to(conn, 18)

        # Verify that after v18, dropped tables are gone
        for table in _DROPPED_TABLES:
            assert not _table_exists(conn, table), f"Table {table} should have been dropped"

        # Verify schema_version records v18
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        assert version == 18

        conn.close()


# ============================================================================
# TS-116-10: Migration v18 preserves retained tables
# ============================================================================


class TestMigrationV18PreservesRetained:
    """TS-116-10: Verify migration v18 does not alter retained tables.

    Requirement: 116-REQ-4.2
    """

    def test_migration_v18_preserves_retained(self) -> None:
        """Retained tables and their data should survive migration v18."""
        conn = duckdb.connect(":memory:")
        # Use pre-v18 schema and apply migrations only to v17
        conn.execute(_PRE_V18_BASE_SCHEMA_DDL)
        _apply_migrations_up_to(conn, 17)

        # Insert test data into retained tables BEFORE v18
        finding = _make_finding(spec_name="test_spec", severity="critical")
        insert_findings(conn, [finding])

        conn.execute(
            "INSERT INTO session_outcomes (id, spec_name, status) "
            "VALUES (gen_random_uuid(), 'test_spec', 'completed')"
        )

        # Apply v18
        _apply_migrations_up_to(conn, 18)

        # Verify retained tables exist and data is intact
        for table in _RETAINED_TABLES:
            assert _table_exists(conn, table), f"Table {table} should still exist"

        assert _count_rows(conn, "review_findings") == 1
        assert _count_rows(conn, "session_outcomes") == 1

        conn.close()


# ============================================================================
# TS-116-11: Migration v18 on fresh database
# ============================================================================


class TestMigrationV18FreshDb:
    """TS-116-11: Verify migration v18 succeeds on a fresh database.

    Requirement: 116-REQ-4.E1
    """

    def test_migration_v18_fresh_db(self) -> None:
        """All migrations v1-v18 should apply without error on a fresh DB."""
        conn = duckdb.connect(":memory:")
        run_migrations(conn)

        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        assert version == 21

        conn.close()


# ============================================================================
# TS-116-12: Supersession without fact_causes
# ============================================================================


class TestSupersessionWithoutFactCauses:
    """TS-116-12: Verify supersession works without fact_causes table.

    Requirements: 116-REQ-5.1, 116-REQ-5.2
    """

    def test_supersession_without_fact_causes(self) -> None:
        """Superseding findings should work without writing to fact_causes."""
        conn = _fresh_conn_with_migrations()

        # Verify fact_causes is gone
        assert not _table_exists(conn, "fact_causes"), "fact_causes should be dropped"

        # Insert initial findings
        old_finding = _make_finding(
            spec_name="test_spec",
            task_group="1",
            session_id="s1",
            description="Old finding",
        )
        insert_findings(conn, [old_finding])

        # Insert new findings for same spec/task_group → supersession
        new_finding = _make_finding(
            spec_name="test_spec",
            task_group="1",
            session_id="s2",
            description="New finding",
        )
        count = insert_findings(conn, [new_finding])
        assert count == 1

        # Only the new finding should be active
        active = query_active_findings(conn, "test_spec")
        assert len(active) == 1
        assert active[0].session_id == "s2"

        conn.close()


# ============================================================================
# TS-116-13: Retrieve returns review findings
# ============================================================================


class TestRetrieveReturnsReviews:
    """TS-116-13: Verify retrieve returns active critical/major findings.

    Requirement: 116-REQ-6.1
    """

    def test_retrieve_returns_reviews(self, knowledge_db: KnowledgeDB) -> None:
        """Retrieve should return critical findings but exclude observations."""
        conn = knowledge_db.connection

        # Insert one critical and one observation finding
        critical_finding = _make_finding(
            spec_name="test_spec",
            severity="critical",
            description="fix X",
            task_group="1",
        )
        observation_finding = _make_finding(
            spec_name="test_spec",
            severity="observation",
            description="note Y",
            task_group="2",  # Different task_group to avoid supersession
        )
        insert_findings(conn, [critical_finding])
        insert_findings(conn, [observation_finding])

        provider = _make_provider(knowledge_db)
        result = provider.retrieve("test_spec", "task")

        assert len(result) == 1
        assert "[REVIEW]" in result[0]
        assert "fix X" in result[0]


# ============================================================================
# TS-116-14: Retrieve empty when no findings
# ============================================================================


class TestRetrieveEmptyNoFindings:
    """TS-116-14: Verify retrieve returns empty list with no findings.

    Requirement: 116-REQ-6.2
    """

    def test_retrieve_empty_no_findings(self, knowledge_db: KnowledgeDB) -> None:
        """Retrieve should return empty list when no findings exist."""
        provider = _make_provider(knowledge_db)
        result = provider.retrieve("empty_spec", "any task")
        assert result == []


# ============================================================================
# TS-116-15: FoxKnowledgeProvider satisfies protocol
# ============================================================================


class TestProviderSatisfiesProtocol:
    """TS-116-15: Verify FoxKnowledgeProvider is a KnowledgeProvider.

    Requirement: 116-REQ-6.3
    """

    def test_provider_satisfies_protocol(self, knowledge_db: KnowledgeDB) -> None:
        """FoxKnowledgeProvider should be an instance of KnowledgeProvider."""
        provider = _make_provider(knowledge_db)
        assert isinstance(provider, KnowledgeProvider)


# ============================================================================
# TS-116-16: Config without gotcha_ttl_days
# ============================================================================


class TestConfigNoGotchaTtl:
    """TS-116-16: Verify KnowledgeProviderConfig has no gotcha_ttl_days.

    Requirement: 116-REQ-7.1
    """

    def test_config_no_gotcha_ttl(self) -> None:
        """KnowledgeProviderConfig should not have gotcha_ttl_days field."""
        config = KnowledgeProviderConfig()
        assert not hasattr(config, "gotcha_ttl_days")


# ============================================================================
# TS-116-17: Config without model_tier
# ============================================================================


class TestConfigNoModelTier:
    """TS-116-17: Verify KnowledgeProviderConfig has no model_tier.

    Requirement: 116-REQ-7.2
    """

    def test_config_no_model_tier(self) -> None:
        """KnowledgeProviderConfig should not have model_tier field."""
        config = KnowledgeProviderConfig()
        assert not hasattr(config, "model_tier")


# ============================================================================
# TS-116-18: Config retains max_items
# ============================================================================


class TestConfigRetainsMaxItems:
    """TS-116-18: Verify KnowledgeProviderConfig has max_items with default 10.

    Requirement: 116-REQ-7.3
    """

    def test_config_retains_max_items(self) -> None:
        """KnowledgeProviderConfig should have max_items defaulting to 10."""
        config = KnowledgeProviderConfig()
        assert config.max_items == 10


# ============================================================================
# TS-116-19: No dead imports in production code
# ============================================================================


class TestNoDeadImports:
    """TS-116-19: Verify no production code imports removed modules.

    Requirement: 116-REQ-8.1
    """

    def test_no_dead_imports(self) -> None:
        """No production code should import removed modules."""
        from pathlib import Path

        removed_modules = [
            "gotcha_extraction",
            "gotcha_store",
            "errata_store",
            "blocking_history",
        ]

        # Search production code for imports of removed modules
        project_root = Path(__file__).parent.parent / "agent_fox"
        violations: list[str] = []

        for py_file in project_root.rglob("*.py"):
            content = py_file.read_text()
            for module in removed_modules:
                # Check for import statements referencing the module
                if f"import {module}" in content or f"from agent_fox.knowledge.{module}" in content:
                    violations.append(f"{py_file.name}: references {module}")

        assert violations == [], f"Dead imports found: {violations}"


# ============================================================================
# TS-116-20: Reset table list updated
# ============================================================================


class TestResetTableList:
    """TS-116-20: Verify reset.py does not list dropped tables.

    Requirement: 116-REQ-8.2
    """

    def test_reset_table_list(self) -> None:
        """reset.py should not reference dropped table names."""
        import agent_fox.engine.reset as reset_module

        source = inspect.getsource(reset_module)
        dropped_tables = [
            "blocking_history",
            "gotchas",
            "errata_index",
            "sleep_artifacts",
            "memory_facts",
            "memory_embeddings",
            "entity_graph",
            "entity_edges",
            "fact_entities",
            "fact_causes",
        ]
        for table in dropped_tables:
            assert f'"{table}"' not in source, (
                f'reset.py should not reference "{table}"'
            )


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestRetrieveMissingTable:
    """TS-116-E1: Verify retrieve returns empty list when review_findings is gone.

    Requirement: 116-REQ-6.E1
    """

    def test_retrieve_missing_table(self) -> None:
        """Retrieve should return empty list when review_findings table is dropped."""
        conn = _fresh_conn_with_migrations()
        conn.execute("DROP TABLE IF EXISTS review_findings")

        db = _create_knowledge_db(conn)
        provider = _make_provider(db)
        result = provider.retrieve("any_spec", "task")
        assert result == []

        conn.close()


class TestConfigIgnoresRemovedFields:
    """TS-116-E2: Verify config silently ignores gotcha_ttl_days and model_tier.

    Requirement: 116-REQ-7.E1
    """

    def test_config_ignores_removed_fields(self) -> None:
        """Config should accept extra fields without error."""
        config = KnowledgeProviderConfig(
            max_items=5,
            gotcha_ttl_days=90,  # type: ignore[call-arg]
            model_tier="SIMPLE",  # type: ignore[call-arg]
        )
        assert config.max_items == 5
        assert not hasattr(config, "gotcha_ttl_days")


class TestGotchasTableExistsNotQueried:
    """TS-116-E3: Verify gotchas table exists but is not queried.

    Requirement: 116-REQ-1.E1
    """

    def test_gotchas_table_exists_not_queried(self) -> None:
        """Even if gotchas table has data, retrieve should not return them."""
        conn = _fresh_conn_with_migrations()

        # If gotchas table still exists (pre-v18 state), create it manually
        # and insert test data
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gotchas (
                id           VARCHAR PRIMARY KEY,
                spec_name    VARCHAR NOT NULL,
                category     VARCHAR NOT NULL DEFAULT 'gotcha',
                text         VARCHAR NOT NULL,
                content_hash VARCHAR NOT NULL,
                session_id   VARCHAR NOT NULL,
                created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "INSERT INTO gotchas (id, spec_name, text, content_hash, session_id) "
            "VALUES ('g1', 'any_spec', 'some gotcha', 'hash1', 's1')"
        )

        db = _create_knowledge_db(conn)
        provider = _make_provider(db)
        result = provider.retrieve("any_spec", "task")
        assert all(not item.startswith("[GOTCHA]") for item in result)

        conn.close()


# ============================================================================
# Property Tests
# ============================================================================


@st.composite
def review_finding_strategy(
    draw: st.DrawFn,
    spec_name: str = "prop_spec",
    task_group: str = "1",
    session_id: str | None = None,
) -> ReviewFinding:
    """Generate a single ReviewFinding with controlled spec/task_group."""
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity=draw(st.sampled_from(["critical", "major", "minor", "observation"])),
        description=draw(st.text(min_size=1, max_size=80, alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
        ))),
        requirement_ref=None,
        spec_name=spec_name,
        task_group=task_group,
        session_id=session_id or f"session-{draw(st.uuids())}",
    )


class TestPropertyReviewCarryforward:
    """TS-116-P1: For any set of review findings, retrieve returns exactly
    the critical/major ones.

    Validates: 116-REQ-6.1, 116-REQ-6.2 (Property 1)
    """

    @given(
        findings=st.lists(
            review_finding_strategy(),
            min_size=0,
            max_size=20,
        ),
    )
    @settings(max_examples=30)
    def test_property_review_carryforward(
        self,
        findings: list[ReviewFinding],
    ) -> None:
        """Retrieve returns exactly critical/major findings as [REVIEW] strings."""
        conn = duckdb.connect(":memory:")
        run_migrations(conn)

        # All findings share the same session_id to insert as one batch
        session_id = f"session-{uuid.uuid4()}"
        normalized = [
            ReviewFinding(
                id=f.id,
                severity=f.severity,
                description=f.description,
                requirement_ref=f.requirement_ref,
                spec_name="prop_spec",
                task_group="1",
                session_id=session_id,
                category=f.category,
            )
            for f in findings
        ]

        if normalized:
            insert_findings(conn, normalized)

        db = _create_knowledge_db(conn)
        provider = _make_provider(db, max_items=len(normalized))
        result = provider.retrieve("prop_spec", "task")

        expected_count = sum(
            1 for f in normalized if f.severity in ("critical", "major")
        )
        assert len(result) == expected_count
        assert all(item.startswith("[REVIEW]") for item in result)

        conn.close()


class TestPropertyNoGotchaErrataLeak:
    """TS-116-P2: For any inputs, retrieve never returns gotcha/errata items.

    Validates: 116-REQ-1.4, 116-REQ-2.2 (Property 2)
    """

    @given(
        spec_name=st.text(min_size=1, max_size=30, alphabet=st.characters(
            whitelist_categories=("L", "N"),
        )),
        task_desc=st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
        )),
    )
    @settings(max_examples=30)
    def test_property_no_gotcha_errata_leak(
        self,
        spec_name: str,
        task_desc: str,
    ) -> None:
        """Retrieve results should only contain [REVIEW] items or be empty."""
        conn = duckdb.connect(":memory:")
        run_migrations(conn)

        db = _create_knowledge_db(conn)
        provider = _make_provider(db)
        result = provider.retrieve(spec_name, task_desc)
        assert all(item.startswith("[REVIEW]") for item in result)

        conn.close()


class TestPropertySupersession:
    """TS-116-P3: For any sequence of finding insertions for the same
    (spec_name, task_group), only the latest batch is active.

    Validates: 116-REQ-5.1, 116-REQ-5.2 (Property 5)
    """

    @given(
        num_batches=st.integers(min_value=2, max_value=5),
        batch_size=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=20)
    def test_property_supersession(
        self,
        num_batches: int,
        batch_size: int,
    ) -> None:
        """After multiple batches, only the last batch's findings are active."""
        conn = duckdb.connect(":memory:")
        run_migrations(conn)

        spec_name = "prop_spec"
        task_group = "1"
        last_session_id = ""

        for i in range(num_batches):
            session_id = f"s{i}"
            last_session_id = session_id
            batch = [
                _make_finding(
                    severity="critical",
                    description=f"Finding {i}-{j}",
                    spec_name=spec_name,
                    task_group=task_group,
                    session_id=session_id,
                )
                for j in range(batch_size)
            ]
            insert_findings(conn, batch)

        active = query_active_findings(conn, spec_name)
        assert len(active) == batch_size
        assert all(f.session_id == last_session_id for f in active)

        conn.close()


# ============================================================================
# Integration Smoke Tests
# ============================================================================


class TestSmokeFullRetrieve:
    """TS-116-SMOKE-1: Full retrieve cycle with review findings.

    Execution Path: Path 1 from design.md
    """

    def test_smoke_full_retrieve(self) -> None:
        """End-to-end: insert critical finding, retrieve through provider."""
        conn = duckdb.connect(":memory:")
        run_migrations(conn)

        db = _create_knowledge_db(conn)
        provider = _make_provider(db)

        # Insert a critical finding
        finding = _make_finding(
            spec_name="s1",
            severity="critical",
            description="critical bug found",
        )
        insert_findings(conn, [finding])

        result = provider.retrieve("s1", "task")
        assert len(result) == 1
        assert result[0].startswith("[REVIEW] [critical]")
        assert "critical bug found" in result[0]

        # Verify no gotcha or errata items
        assert all(not item.startswith("[GOTCHA]") for item in result)
        assert all(not item.startswith("[ERRATA]") for item in result)

        conn.close()


class TestSmokeIngestThenRetrieve:
    """TS-116-SMOKE-2: Ingest then retrieve produces no gotchas.

    Execution Path: Path 2 + Path 1 from design.md
    """

    def test_smoke_ingest_then_retrieve(self) -> None:
        """Ingest should be a no-op; subsequent retrieve returns empty list."""
        conn = duckdb.connect(":memory:")
        run_migrations(conn)

        db = _create_knowledge_db(conn)
        provider = _make_provider(db)

        # Ingest a completed session
        provider.ingest(
            "s1",
            "spec_01",
            {
                "session_status": "completed",
                "touched_files": ["main.rs"],
                "commit_sha": "abc",
            },
        )

        # Retrieve should return empty (no findings, no gotchas)
        result = provider.retrieve("spec_01", "task")
        assert result == []

        conn.close()


class TestSmokeMigrationWithData:
    """TS-116-SMOKE-3: Full migration on existing database with data.

    Execution Path: Migration path from design.md
    """

    def test_smoke_migration_with_data(self) -> None:
        """Migrations v1-v18 on a DB with data should produce correct state."""
        conn = duckdb.connect(":memory:")
        # Apply migrations up to v17 using pre-v18 schema (includes dropped tables)
        conn.execute(_PRE_V18_BASE_SCHEMA_DDL)
        _apply_migrations_up_to(conn, 17)

        # Insert test data into to-be-dropped tables BEFORE v18
        conn.execute(
            "INSERT INTO gotchas (id, spec_name, text, content_hash, session_id) "
            "VALUES ('g1', 'test_spec', 'test gotcha', 'hash1', 's1')"
        )
        conn.execute(
            "INSERT INTO memory_facts (id, content, spec_name) "
            "VALUES (gen_random_uuid(), 'test memory fact', 'test_spec')"
        )
        assert _count_rows(conn, "gotchas") == 1
        assert _count_rows(conn, "memory_facts") == 1

        # Insert test data into retained tables BEFORE v18
        finding = _make_finding(spec_name="test_spec", severity="critical")
        insert_findings(conn, [finding])

        # Apply v18
        _apply_migrations_up_to(conn, 18)

        # All dropped tables should be gone
        for table in _DROPPED_TABLES:
            assert not _table_exists(conn, table), f"{table} should be dropped"

        # Retained tables should exist with data intact
        assert _table_exists(conn, "review_findings")
        assert _count_rows(conn, "review_findings") == 1

        # Schema version should be exactly 18
        version = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()[0]
        assert version == 18

        conn.close()
