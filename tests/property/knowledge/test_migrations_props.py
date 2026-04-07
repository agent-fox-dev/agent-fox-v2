"""Property tests for migration version monotonicity.

Test Spec: TS-11-P2 (migration version monotonicity)
Property: Property 2 from design.md
Requirements: 11-REQ-3.1, 11-REQ-3.3
"""

from __future__ import annotations

from unittest.mock import patch

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.migrations import (
    Migration,
    apply_pending_migrations,
)
from tests.unit.knowledge.conftest import create_schema


def _make_test_migrations(count: int) -> list[Migration]:
    """Create a sequence of test migrations for property testing.

    Each migration adds a uniquely-named column to session_outcomes to
    avoid conflicts between migrations.
    """
    migrations = []
    for i in range(count):
        version = i + 2  # start after version 1 (initial schema)
        col_name = f"prop_test_col_{version}"
        migrations.append(
            Migration(
                version=version,
                description=f"add {col_name}",
                apply=lambda c, cn=col_name: c.execute(f"ALTER TABLE session_outcomes ADD COLUMN {cn} TEXT"),  # type: ignore[arg-type,misc]
            )
        )
    return migrations


class TestMigrationVersionMonotonicity:
    """TS-11-P2: Migration version monotonicity.

    For any sequence of 1-3 migrations, the versions in schema_version
    are strictly increasing.

    Property 2 from design.md.
    """

    @given(migration_count=st.integers(min_value=1, max_value=3))
    @settings(max_examples=3)
    def test_versions_strictly_increasing(self, migration_count: int) -> None:
        """Schema versions are strictly increasing after N migrations."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        test_migrations = _make_test_migrations(migration_count)

        with patch(
            "agent_fox.knowledge.migrations.MIGRATIONS",
            test_migrations,
        ):
            apply_pending_migrations(conn)

        versions = [r[0] for r in conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()]

        # Verify strict monotonicity
        for i in range(1, len(versions)):
            assert versions[i] > versions[i - 1]

        conn.close()
