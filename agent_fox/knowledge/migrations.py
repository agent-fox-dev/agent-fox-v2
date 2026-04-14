"""Schema version table, forward-only migration runner, migration registry.

Requirements: 11-REQ-3.1, 11-REQ-3.2, 11-REQ-3.3, 11-REQ-3.E1,
              27-REQ-1.1, 27-REQ-1.2, 27-REQ-2.1, 27-REQ-2.2
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import duckdb  # noqa: F401

from agent_fox.core.errors import KnowledgeStoreError  # noqa: F401

logger = logging.getLogger("agent_fox.knowledge.migrations")

_ALLOWED_EMBEDDING_DIMS = frozenset({384, 768, 1536})
_DEFAULT_EMBEDDING_DIM = 384


def _sanitize_embedding_dim(dim: int) -> int:
    """Return *dim* if it is an allowed embedding dimension, else the default."""
    return dim if dim in _ALLOWED_EMBEDDING_DIMS else _DEFAULT_EMBEDDING_DIM


MigrationFn = Callable[[duckdb.DuckDBPyConnection], None]


@dataclass(frozen=True)
class Migration:
    """A forward-only schema migration."""

    version: int
    description: str
    apply: MigrationFn


def _migrate_v2(conn: duckdb.DuckDBPyConnection) -> None:
    """Add review_findings and verification_results tables.

    Requirements: 27-REQ-1.1, 27-REQ-1.2, 27-REQ-2.1, 27-REQ-2.2
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS review_findings (
            id              UUID PRIMARY KEY,
            severity        TEXT NOT NULL,
            description     TEXT NOT NULL,
            requirement_ref TEXT,
            spec_name       TEXT NOT NULL,
            task_group      TEXT NOT NULL,
            session_id      TEXT NOT NULL,
            superseded_by   TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS verification_results (
            id              UUID PRIMARY KEY,
            requirement_id  TEXT NOT NULL,
            verdict         TEXT NOT NULL,
            evidence        TEXT,
            spec_name       TEXT NOT NULL,
            task_group      TEXT NOT NULL,
            session_id      TEXT NOT NULL,
            superseded_by   TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)


def _migrate_v3(conn: duckdb.DuckDBPyConnection) -> None:
    """Add complexity_assessments and execution_outcomes tables.

    Requirements: 30-REQ-6.1, 30-REQ-6.2, 30-REQ-6.3, 30-REQ-6.E1
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS complexity_assessments (
            id              VARCHAR PRIMARY KEY,
            node_id         VARCHAR NOT NULL,
            spec_name       VARCHAR NOT NULL,
            task_group      INTEGER NOT NULL,
            predicted_tier  VARCHAR NOT NULL,
            confidence      FLOAT NOT NULL,
            assessment_method VARCHAR NOT NULL,
            feature_vector  JSON NOT NULL,
            tier_ceiling    VARCHAR NOT NULL,
            created_at      TIMESTAMP NOT NULL DEFAULT current_timestamp
        );

        CREATE TABLE IF NOT EXISTS execution_outcomes (
            id                  VARCHAR PRIMARY KEY,
            assessment_id       VARCHAR NOT NULL REFERENCES complexity_assessments(id),
            actual_tier         VARCHAR NOT NULL,
            total_tokens        INTEGER NOT NULL,
            total_cost          FLOAT NOT NULL,
            duration_ms         INTEGER NOT NULL,
            attempt_count       INTEGER NOT NULL,
            escalation_count    INTEGER NOT NULL,
            outcome             VARCHAR NOT NULL,
            files_touched_count INTEGER NOT NULL,
            created_at          TIMESTAMP NOT NULL DEFAULT current_timestamp
        );
    """)


def _migrate_v4(conn: duckdb.DuckDBPyConnection) -> None:
    """Add drift_findings table for Oracle archetype.

    Requirements: 32-REQ-7.2
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drift_findings (
            id UUID PRIMARY KEY,
            severity VARCHAR NOT NULL,
            description VARCHAR NOT NULL,
            spec_ref VARCHAR,
            artifact_ref VARCHAR,
            spec_name VARCHAR NOT NULL,
            task_group VARCHAR NOT NULL,
            session_id VARCHAR NOT NULL,
            superseded_by UUID,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)


def _migrate_v5(conn: duckdb.DuckDBPyConnection) -> None:
    """Convert memory_facts.confidence from TEXT to FLOAT.

    Uses the canonical mapping: high -> 0.9, medium -> 0.6, low -> 0.3.
    Unknown or NULL values default to 0.6.

    DuckDB does not allow ALTER TABLE DROP COLUMN when foreign keys
    reference the table, so we recreate the table with the new schema
    and copy data over.

    Requirements: 37-REQ-2.1, 37-REQ-2.2, 37-REQ-2.3, 37-REQ-2.E1
    """
    # Check if memory_facts table exists; skip if not
    tables = {
        r[0]
        for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()
    }
    if "memory_facts" not in tables:
        logger.info("memory_facts table not found, skipping v5 migration")
        return

    # Check if confidence column is already numeric (idempotency)
    col_info = conn.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'memory_facts' AND column_name = 'confidence'"
    ).fetchone()
    if col_info and col_info[0].upper() in ("FLOAT", "DOUBLE"):
        logger.info("memory_facts.confidence already numeric, skipping v5 migration")
        return

    # Step 1: Create a temp table with the new DOUBLE column
    conn.execute("""
        CREATE TABLE memory_facts_new (
            id            UUID PRIMARY KEY,
            content       TEXT NOT NULL,
            category      TEXT,
            spec_name     TEXT,
            session_id    TEXT,
            commit_sha    TEXT,
            confidence    DOUBLE DEFAULT 0.6,
            created_at    TIMESTAMP,
            superseded_by UUID
        )
    """)

    # Step 2: Copy data with canonical mapping conversion
    conn.execute("""
        INSERT INTO memory_facts_new
            (id, content, category, spec_name, session_id, commit_sha,
             confidence, created_at, superseded_by)
        SELECT id, content, category, spec_name, session_id, commit_sha,
            CASE
                WHEN confidence = 'high' THEN 0.9
                WHEN confidence = 'medium' THEN 0.6
                WHEN confidence = 'low' THEN 0.3
                WHEN confidence IS NULL THEN 0.6
                ELSE 0.6
            END,
            created_at, superseded_by
        FROM memory_facts
    """)

    # Step 3: Drop dependent tables temporarily, swap, recreate deps
    # Save embeddings data if it exists
    has_embeddings = False
    try:
        row = conn.execute("SELECT COUNT(*) FROM memory_embeddings").fetchone()
        has_embeddings = row is not None and row[0] > 0
    except Exception:
        pass

    if has_embeddings:
        conn.execute("CREATE TEMP TABLE embeddings_backup AS SELECT * FROM memory_embeddings")

    # Drop memory_embeddings (depends on memory_facts via FK)
    conn.execute("DROP TABLE IF EXISTS memory_embeddings")

    # Swap tables
    conn.execute("DROP TABLE memory_facts")
    conn.execute("ALTER TABLE memory_facts_new RENAME TO memory_facts")

    # Recreate memory_embeddings with FK to new memory_facts
    # Detect embedding dimensions from backup if available
    dim = _DEFAULT_EMBEDDING_DIM
    try:
        col_info = conn.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'embeddings_backup' AND column_name = 'embedding'"
        ).fetchone()
        if col_info:
            dim_str = col_info[0]
            # Parse "FLOAT[N]" format
            import re

            m = re.search(r"\[(\d+)\]", dim_str)
            if m:
                dim = _sanitize_embedding_dim(int(m.group(1)))
    except Exception:
        pass

    conn.execute(f"""
        CREATE TABLE memory_embeddings (
            id        UUID PRIMARY KEY REFERENCES memory_facts(id),
            embedding FLOAT[{dim}]
        )
    """)

    if has_embeddings:
        conn.execute("INSERT INTO memory_embeddings SELECT * FROM embeddings_backup")
        conn.execute("DROP TABLE embeddings_backup")


def _migrate_v6(conn: duckdb.DuckDBPyConnection) -> None:
    """Add audit_events table.

    Requirements: 40-REQ-3.1, 40-REQ-3.2
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id          VARCHAR PRIMARY KEY,
            timestamp   TIMESTAMP NOT NULL,
            run_id      VARCHAR NOT NULL,
            event_type  VARCHAR NOT NULL,
            node_id     VARCHAR,
            session_id  VARCHAR,
            archetype   VARCHAR,
            severity    VARCHAR NOT NULL,
            payload     JSON NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_run_id
            ON audit_events (run_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_event_type
            ON audit_events (event_type)
    """)


def _migrate_v7(conn: duckdb.DuckDBPyConnection) -> None:
    """Add category column to review_findings table.

    Enables classification of findings (e.g. 'security', 'correctness',
    'performance'). Critical security-category findings bypass the numeric
    block threshold and always trigger blocking.

    Requirements: 277-REQ-1, 277-REQ-2
    """
    conn.execute("ALTER TABLE review_findings ADD COLUMN IF NOT EXISTS category TEXT")


def _migrate_v10(conn: duckdb.DuckDBPyConnection) -> None:
    """Add keywords column to memory_facts table.

    Enables fingerprint-based deduplication for git pattern mining,
    LLM code analysis, and documentation mining in the onboarding
    pipeline. Existing rows receive an empty array (the column default).

    DuckDB 1.5.x blocks ALTER TABLE on memory_facts because memory_embeddings
    holds a FK reference to it (same bug as v5 migration). The workaround is:
    1. Back up embeddings if any exist.
    2. Drop memory_embeddings (removes the FK dependency).
    3. Add the keywords column to memory_facts.
    4. Recreate memory_embeddings and restore data.

    See docs/errata/101_keywords_schema_migration.md for context.

    Requirements: 101-REQ-4.E3, 101-REQ-5.6, 101-REQ-6.6, 101-REQ-8.2
    """
    # Check if memory_facts table exists; skip if not
    tables = {
        r[0]
        for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()
    }
    if "memory_facts" not in tables:
        logger.info("memory_facts table not found, skipping v10 migration")
        return

    # Idempotency check — skip if column already exists
    col_info = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'memory_facts' AND column_name = 'keywords'"
    ).fetchone()
    if col_info is not None:
        logger.info("memory_facts.keywords already exists, skipping v10 migration")
        return

    # Detect current embedding dimension from memory_embeddings
    dim = _DEFAULT_EMBEDDING_DIM
    try:
        col_type_info = conn.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'memory_embeddings' AND column_name = 'embedding'"
        ).fetchone()
        if col_type_info:
            import re

            m = re.search(r"\[(\d+)\]", col_type_info[0])
            if m:
                dim = _sanitize_embedding_dim(int(m.group(1)))
    except Exception:
        pass

    # Back up existing embeddings (DuckDB won't let us ALTER while FK exists)
    has_embeddings = False
    try:
        row = conn.execute("SELECT COUNT(*) FROM memory_embeddings").fetchone()
        has_embeddings = row is not None and row[0] > 0
    except Exception:
        pass

    if has_embeddings:
        conn.execute("CREATE TEMP TABLE embeddings_backup AS SELECT * FROM memory_embeddings")

    # Drop the FK-dependent table so ALTER TABLE can proceed
    conn.execute("DROP TABLE IF EXISTS memory_embeddings")

    # Add the keywords column
    conn.execute("ALTER TABLE memory_facts ADD COLUMN keywords TEXT[] DEFAULT []")

    # Recreate memory_embeddings with FK restored
    conn.execute(f"""
        CREATE TABLE memory_embeddings (
            id        UUID PRIMARY KEY REFERENCES memory_facts(id),
            embedding FLOAT[{dim}]
        )
    """)

    if has_embeddings:
        conn.execute("INSERT INTO memory_embeddings SELECT * FROM embeddings_backup")
        conn.execute("DROP TABLE embeddings_backup")


def _migrate_v8(conn: duckdb.DuckDBPyConnection) -> None:
    """Add entity_graph, entity_edges, and fact_entities tables.

    FK constraints on entity_edges and fact_entities are intentionally omitted
    due to a DuckDB 1.5.x bug where FK checks incorrectly block UPDATE statements
    on referenced tables even when the referenced column value does not change.
    Referential integrity is enforced at the application layer in entity_store.py.
    See docs/errata/95_entity_graph.md for details.

    Requirements: 95-REQ-1.1, 95-REQ-2.1, 95-REQ-3.1
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_graph (
            id           UUID PRIMARY KEY,
            entity_type  VARCHAR NOT NULL,
            entity_name  VARCHAR NOT NULL,
            entity_path  VARCHAR NOT NULL,
            created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at   TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS entity_edges (
            source_id    UUID NOT NULL,
            target_id    UUID NOT NULL,
            relationship VARCHAR NOT NULL,
            PRIMARY KEY (source_id, target_id, relationship)
        );

        CREATE TABLE IF NOT EXISTS fact_entities (
            fact_id      UUID NOT NULL,
            entity_id    UUID NOT NULL,
            PRIMARY KEY (fact_id, entity_id)
        );

        CREATE INDEX IF NOT EXISTS idx_entity_natural_key
            ON entity_graph(entity_type, entity_path, entity_name);
        CREATE INDEX IF NOT EXISTS idx_entity_deleted
            ON entity_graph(deleted_at);
        CREATE INDEX IF NOT EXISTS idx_entity_path
            ON entity_graph(entity_path);
        CREATE INDEX IF NOT EXISTS idx_edge_source ON entity_edges(source_id);
        CREATE INDEX IF NOT EXISTS idx_edge_target ON entity_edges(target_id);
        CREATE INDEX IF NOT EXISTS idx_fact_entity_entity ON fact_entities(entity_id);
    """)


def _migrate_v9(conn: duckdb.DuckDBPyConnection) -> None:
    """Add language column to entity_graph and backfill existing rows.

    Adds a nullable VARCHAR column so every entity can be tagged with the
    source language that produced it (e.g. 'python', 'go', 'typescript').
    Pre-existing entities are backfilled with 'python' because all entities
    created before this migration were produced by the Python analyzer.

    Uses IF NOT EXISTS so the migration is safe to run multiple times.

    Requirements: 102-REQ-5.1, 102-REQ-5.2, 102-REQ-5.E1
    """
    conn.execute("ALTER TABLE entity_graph ADD COLUMN IF NOT EXISTS language VARCHAR")
    conn.execute("UPDATE entity_graph SET language = 'python' WHERE language IS NULL")


# Registry of all migrations, ordered by version.
MIGRATIONS: list[Migration] = [
    Migration(
        version=2,
        description="add review_findings and verification_results tables",
        apply=_migrate_v2,
    ),
    Migration(
        version=3,
        description="add complexity_assessments and execution_outcomes tables",
        apply=_migrate_v3,
    ),
    Migration(
        version=4,
        description="add drift_findings table for oracle archetype",
        apply=_migrate_v4,
    ),
    Migration(
        version=5,
        description="convert memory_facts.confidence from TEXT to FLOAT",
        apply=_migrate_v5,
    ),
    Migration(
        version=6,
        description="add audit_events table",
        apply=_migrate_v6,
    ),
    Migration(
        version=7,
        description="add category column to review_findings for security classification",
        apply=_migrate_v7,
    ),
    Migration(
        version=8,
        description="add entity_graph, entity_edges, and fact_entities tables",
        apply=_migrate_v8,
    ),
    Migration(
        version=9,
        description="add language column to entity_graph for multi-language support",
        apply=_migrate_v9,
    ),
    Migration(
        version=10,
        description="add keywords column to memory_facts for fingerprint-based deduplication",
        apply=_migrate_v10,
    ),
]


# ---------------------------------------------------------------------------
# Base schema DDL for fresh databases (used by run_migrations)
# ---------------------------------------------------------------------------

_BASE_SCHEMA_DDL = """
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
    id         UUID PRIMARY KEY,
    session_id TEXT,
    node_id    TEXT,
    tool_name  TEXT,
    failed_at  TIMESTAMP
);

INSERT INTO schema_version (version, description)
    SELECT 1, 'initial schema'
    WHERE NOT EXISTS (SELECT 1 FROM schema_version WHERE version = 1);
"""


def run_migrations(conn: duckdb.DuckDBPyConnection) -> None:
    """Initialize base schema and apply all pending migrations.

    Convenience function for tests and the onboarding pipeline that need a
    fully initialized database without going through the full
    ``KnowledgeDB.open()`` path (which loads VSS and creates the embedding
    table with a configurable dimension).

    Creates all base tables (including ``memory_facts`` with the
    ``keywords`` column) and runs every registered migration.

    Args:
        conn: An open DuckDB connection (in-memory or file-backed).
    """
    conn.execute(_BASE_SCHEMA_DDL)
    apply_pending_migrations(conn)


def get_current_version(conn: duckdb.DuckDBPyConnection) -> int:
    """Return the current schema version, or 0 if no version table."""
    try:
        result = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    except duckdb.CatalogException:
        # schema_version table does not exist yet
        return 0
    if result is None or result[0] is None:
        return 0
    return int(result[0])


def apply_pending_migrations(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply all migrations newer than the current schema version.

    Each migration runs in its own transaction. On failure, raises
    KnowledgeStoreError with the failing version and cause.
    """
    current = get_current_version(conn)

    for migration in MIGRATIONS:
        if migration.version <= current:
            continue
        try:
            migration.apply(conn)
            record_version(conn, migration.version, migration.description)
            logger.info(
                "Applied migration v%d: %s",
                migration.version,
                migration.description,
            )
        except KnowledgeStoreError:
            raise
        except Exception as exc:
            raise KnowledgeStoreError(
                f"Migration to version {migration.version} failed: {exc}",
                version=migration.version,
            ) from exc


def record_version(
    conn: duckdb.DuckDBPyConnection,
    version: int,
    description: str,
) -> None:
    """Insert a row into schema_version."""
    conn.execute(
        "INSERT INTO schema_version (version, description) VALUES (?, ?)",
        [version, description],
    )
