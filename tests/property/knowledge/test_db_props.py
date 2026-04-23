"""Property tests for schema initialization idempotency.

Test Spec: TS-11-P1 (schema initialization idempotency)
Property: Property 1 from design.md
Requirements: 11-REQ-2.1, 11-REQ-2.2
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import KnowledgeConfig
from agent_fox.knowledge.db import KnowledgeDB

# -- Expected tables in the knowledge store schema ---------------------------

EXPECTED_TABLES = {
    "schema_version",
    "session_outcomes",
    "tool_calls",
    "tool_errors",
    "review_findings",
    "verification_results",
    "drift_findings",
    "audit_events",
    # Added by migration v11 (spec 105: DB-based plan state)
    "plan_nodes",
    "plan_edges",
    "plan_meta",
    "runs",
    # Added by migration v19 (issue #522: errata generation)
    "errata",
}


class TestSchemaInitializationIdempotency:
    """TS-11-P1: Schema initialization idempotency.

    For any N in [1, 5], opening and initializing the same database N times
    produces identical schema state: exactly 2 version rows and all 9 tables.

    Property 1 from design.md.
    """

    @given(n=st.integers(min_value=1, max_value=5))
    @settings(max_examples=5, deadline=None)
    def test_n_open_close_cycles_produce_same_state(self, n: int, tmp_path_factory: object) -> None:
        """Opening the database N times yields exactly 2 version rows and 9 tables."""
        # Use a unique path per hypothesis example
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "knowledge.duckdb"
            config = KnowledgeConfig(store_path=str(db_path))

            for _ in range(n):
                db = KnowledgeDB(config)
                db.open()
                db.close()

            # Final verification
            db = KnowledgeDB(config)
            db.open()

            version_count = db.connection.execute("SELECT COUNT(*) FROM schema_version").fetchone()
            assert version_count is not None
            assert version_count[0] == 20

            tables = {r[0] for r in db.connection.execute("SHOW TABLES").fetchall()}
            assert tables == EXPECTED_TABLES

            db.close()
