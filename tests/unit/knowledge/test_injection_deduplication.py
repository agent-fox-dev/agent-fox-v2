"""Tests for knowledge injection deduplication tracking (issue #558).

Verifies that findings injected into a session are recorded and subsequently
superseded when the session completes successfully, preventing re-injection
into future sessions.

Acceptance Criteria: 558-AC-1, 558-AC-2, 558-AC-3, 558-AC-4, 558-AC-5
"""

from __future__ import annotations

import uuid

import duckdb
import pytest

from agent_fox.knowledge.migrations import get_current_version, run_migrations
from agent_fox.knowledge.review_store import (
    ReviewFinding,
    VerificationResult,
    insert_findings,
    insert_verdicts,
    query_active_findings,
    query_active_verdicts,
    record_finding_injections,
    supersede_injected_findings,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with fully migrated schema (through v23)."""
    c = duckdb.connect(":memory:")
    run_migrations(c)
    yield c
    c.close()


@pytest.fixture()
def provider_db(conn: duckdb.DuckDBPyConnection):
    """KnowledgeDB wrapper around the migrated connection."""
    from agent_fox.knowledge.db import KnowledgeDB

    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = conn
    return db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    spec_name: str,
    *,
    task_group: str | None = None,
    session_id: str = "reviewer:1",
    severity: str = "critical",
    description: str = "Test finding",
) -> ReviewFinding:
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group=task_group or str(uuid.uuid4()),
        session_id=session_id,
    )


def _make_verdict(
    spec_name: str,
    *,
    task_group: str | None = None,
    session_id: str = "verifier:1",
    verdict: str = "FAIL",
    requirement_id: str = "REQ-1",
) -> VerificationResult:
    return VerificationResult(
        id=str(uuid.uuid4()),
        requirement_id=requirement_id,
        verdict=verdict,
        evidence="Evidence text",
        spec_name=spec_name,
        task_group=task_group or str(uuid.uuid4()),
        session_id=session_id,
    )


def _make_provider(provider_db):
    """Construct FoxKnowledgeProvider with default config."""
    from agent_fox.core.config import KnowledgeProviderConfig
    from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

    return FoxKnowledgeProvider(provider_db, KnowledgeProviderConfig())


# ===========================================================================
# AC-5: Migration v23 creates finding_injections table
# ===========================================================================


class TestMigrationV23:
    """AC-5: Migration v23 creates the finding_injections table idempotently.

    Requirements: 558-AC-5
    """

    def test_schema_version_is_23(self, conn: duckdb.DuckDBPyConnection) -> None:
        """AC-5: After run_migrations, schema version >= 23."""
        version = get_current_version(conn)
        assert version >= 23, f"Expected schema version >= 23, got {version}"

    def test_finding_injections_table_exists(self, conn: duckdb.DuckDBPyConnection) -> None:
        """AC-5: finding_injections table is present after migration."""
        row = conn.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = 'finding_injections'"
        ).fetchone()
        assert row is not None, "finding_injections table must exist after v23 migration"

    def test_finding_injections_columns(self, conn: duckdb.DuckDBPyConnection) -> None:
        """AC-5: finding_injections has exactly the expected columns."""
        cols = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'finding_injections'"
            ).fetchall()
        }
        assert cols == {"id", "finding_id", "session_id", "injected_at"}, (
            f"Unexpected columns in finding_injections: {cols}"
        )

    def test_migration_is_idempotent(self) -> None:
        """AC-5: Running migrations twice does not raise an error."""
        c = duckdb.connect(":memory:")
        run_migrations(c)
        # Second run should be a no-op — no error raised
        run_migrations(c)
        c.close()


# ===========================================================================
# AC-1: retrieve() records injected finding IDs
# ===========================================================================


class TestRetrieveRecordsInjections:
    """AC-1: retrieve() with session_id records returned finding/verdict IDs.

    Requirements: 558-AC-1
    """

    def test_ac1_finding_id_appears_in_finding_injections(
        self, provider_db, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-1: After retrieve(session_id=...), the finding ID is in finding_injections."""
        finding = _make_finding("S", task_group="1")
        insert_findings(conn, [finding])

        provider = _make_provider(provider_db)
        result = provider.retrieve("S", "", task_group="1", session_id="S:1:coder")

        # Finding should have been returned
        assert any("[REVIEW]" in item for item in result), (
            f"Expected a [REVIEW] item in result, got: {result}"
        )

        # Finding ID must appear in finding_injections for this session
        count = conn.execute(
            "SELECT COUNT(*) FROM finding_injections WHERE session_id = 'S:1:coder'"
        ).fetchone()[0]
        assert count == 1, (
            f"Expected 1 injection record for S:1:coder, got {count}"
        )

    def test_ac1_verdict_id_appears_in_finding_injections(
        self, provider_db, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-1: retrieve() also records verdict IDs in finding_injections."""
        verdict = _make_verdict("S", task_group="1")
        insert_verdicts(conn, [verdict])

        provider = _make_provider(provider_db)
        provider.retrieve("S", "", task_group="1", session_id="S:1:coder")

        count = conn.execute(
            "SELECT COUNT(*) FROM finding_injections WHERE session_id = 'S:1:coder'"
        ).fetchone()[0]
        assert count == 1, f"Expected 1 verdict injection record, got {count}"

    def test_ac1_no_recording_when_session_id_omitted(
        self, provider_db, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-1 backward-compat: no injection log written when session_id is None."""
        finding = _make_finding("S", task_group="1")
        insert_findings(conn, [finding])

        provider = _make_provider(provider_db)
        provider.retrieve("S", "", task_group="1")  # no session_id

        count = conn.execute("SELECT COUNT(*) FROM finding_injections").fetchone()[0]
        assert count == 0, "No injection records expected when session_id is omitted"

    def test_ac1_multiple_findings_all_recorded(
        self, provider_db, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-1: Each finding returned by retrieve() has its own injection record."""
        # Two independent findings (unique task_groups to avoid supersession)
        f1 = _make_finding("S", task_group="tg-a", description="first finding")
        f2 = _make_finding("S", task_group="tg-b", description="second finding")
        insert_findings(conn, [f1])
        insert_findings(conn, [f2])

        provider = _make_provider(provider_db)
        provider.retrieve("S", "", session_id="sess-X")

        count = conn.execute(
            "SELECT COUNT(*) FROM finding_injections WHERE session_id = 'sess-X'"
        ).fetchone()[0]
        assert count == 2, f"Expected 2 injection records (one per finding), got {count}"

    def test_ac1_duplicate_retrieve_does_not_duplicate_records(
        self, provider_db, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-1 idempotency: calling retrieve() twice for the same session does not
        create duplicate rows in finding_injections."""
        finding = _make_finding("S", task_group="1")
        insert_findings(conn, [finding])

        provider = _make_provider(provider_db)
        provider.retrieve("S", "", task_group="1", session_id="sess-dup")
        provider.retrieve("S", "", task_group="1", session_id="sess-dup")

        count = conn.execute(
            "SELECT COUNT(*) FROM finding_injections WHERE session_id = 'sess-dup'"
        ).fetchone()[0]
        assert count == 1, (
            f"Expected exactly 1 record after duplicate retrieve() calls, got {count}"
        )


# ===========================================================================
# AC-2: ingest() supersedes injected findings on successful completion
# ===========================================================================


class TestIngestSupersedes:
    """AC-2: ingest() with session_status='completed' supersedes injected findings.

    Requirements: 558-AC-2
    """

    def test_ac2_finding_superseded_after_successful_ingest(
        self, provider_db, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-2: F1 injected into session S1 is superseded after ingest() with
        session_status='completed'.  query_active_findings returns no F1 afterwards.
        """
        finding = _make_finding("S", task_group="1", description="auth bypass")
        insert_findings(conn, [finding])

        provider = _make_provider(provider_db)
        # Step 1: inject into session S1
        provider.retrieve("S", "", task_group="1", session_id="S:1:coder")

        # Verify still active before ingest
        active_before = query_active_findings(conn, "S", task_group="1")
        assert len(active_before) == 1, "Finding should be active before ingest()"

        # Step 2: simulate successful session completion
        provider.ingest(
            "S:1:coder",
            "S",
            {"session_status": "completed", "touched_files": [], "project_root": ""},
        )

        # Step 3: finding must now be superseded
        active_after = query_active_findings(conn, "S", task_group="1")
        assert len(active_after) == 0, (
            f"Finding should be superseded after successful ingest(), still active: {active_after}"
        )

    def test_ac2_superseded_by_set_to_session_id(
        self, provider_db, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-2: The superseded_by column is set to the coder session_id."""
        finding = _make_finding("S", task_group="1")
        insert_findings(conn, [finding])

        provider = _make_provider(provider_db)
        provider.retrieve("S", "", task_group="1", session_id="S:1:coder")
        provider.ingest(
            "S:1:coder",
            "S",
            {"session_status": "completed", "touched_files": [], "project_root": ""},
        )

        row = conn.execute(
            "SELECT superseded_by::VARCHAR FROM review_findings WHERE id::VARCHAR = ?",
            [finding.id],
        ).fetchone()
        assert row is not None
        assert row[0] == "S:1:coder", (
            f"Expected superseded_by='S:1:coder', got {row[0]!r}"
        )

    def test_ac2_verdict_superseded_after_successful_ingest(
        self, provider_db, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-2: FAIL verdict injected into session is superseded on completion."""
        verdict = _make_verdict("S", task_group="1", requirement_id="REQ-AUTH")
        insert_verdicts(conn, [verdict])

        provider = _make_provider(provider_db)
        provider.retrieve("S", "", task_group="1", session_id="S:1:coder")

        active_before = query_active_verdicts(conn, "S", task_group="1")
        assert len(active_before) == 1

        provider.ingest(
            "S:1:coder",
            "S",
            {"session_status": "completed", "touched_files": [], "project_root": ""},
        )

        active_after = query_active_verdicts(conn, "S", task_group="1")
        assert len(active_after) == 0, (
            "FAIL verdict should be superseded after successful ingest()"
        )

    def test_ac2_finding_not_superseded_if_not_injected(
        self, provider_db, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-2: A finding that was NOT injected into a session is not superseded
        when that session's ingest() is called."""
        # Insert finding but do NOT call retrieve() for this session
        finding = _make_finding("S", task_group="1")
        insert_findings(conn, [finding])

        provider = _make_provider(provider_db)
        # Ingest directly without prior retrieve() for "S:1:coder"
        provider.ingest(
            "S:1:coder",
            "S",
            {"session_status": "completed", "touched_files": [], "project_root": ""},
        )

        # Finding should still be active — it was never injected into this session
        active = query_active_findings(conn, "S", task_group="1")
        assert len(active) == 1, (
            "Finding should remain active if it was not injected into the completed session"
        )


# ===========================================================================
# AC-3: Failed sessions do not supersede findings
# ===========================================================================


class TestFailedSessionDoesNotSupersede:
    """AC-3: A failed session leaves findings active so retry sessions see them.

    Requirements: 558-AC-3
    """

    def test_ac3_finding_still_active_after_failed_session(
        self, provider_db, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-3: F1 injected into S1 (attempt 1, which failed) is still
        returned by query_active_findings after the failed attempt — because
        ingest() is never called for failed sessions.
        """
        finding = _make_finding("S", task_group="1")
        insert_findings(conn, [finding])

        provider = _make_provider(provider_db)
        # Attempt 1: retrieve() injects F1 into session S:1:coder
        result = provider.retrieve("S", "", task_group="1", session_id="S:1:coder")
        assert any("[REVIEW]" in item for item in result), "Finding should be returned"

        # Session fails — ingest() is NOT called (as per real lifecycle in session_lifecycle.py)
        # Simulate this by calling ingest with "failed" status to confirm it's a no-op.
        provider.ingest(
            "S:1:coder",
            "S",
            {"session_status": "failed", "touched_files": [], "project_root": ""},
        )

        # F1 must still be active for the retry session
        active = query_active_findings(conn, "S", task_group="1")
        assert len(active) == 1, (
            f"Finding must remain active after failed session, got: {active}"
        )

    def test_ac3_retry_session_sees_finding(
        self, provider_db, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-3: The retry session's retrieve() still returns F1 because it was
        never superseded (the prior session failed)."""
        finding = _make_finding("S", task_group="1", description="unresolved bug")
        insert_findings(conn, [finding])

        provider = _make_provider(provider_db)
        # Attempt 1 injects F1
        provider.retrieve("S", "", task_group="1", session_id="S:1:coder")

        # Session fails (no ingest)
        # Attempt 2 (retry) should still see F1
        result_retry = provider.retrieve("S", "", task_group="1", session_id="S:1:coder")
        assert any("unresolved bug" in item for item in result_retry), (
            "Retry session must see the finding that was not addressed by the failed attempt"
        )


# ===========================================================================
# AC-4: session_lifecycle passes session_id to retrieve()
# ===========================================================================


class TestSessionLifecyclePassesSessionId:
    """AC-4: _build_prompts() passes self._node_id as session_id to retrieve().

    Requirements: 558-AC-4
    """

    def test_ac4_retrieve_call_includes_session_id(self) -> None:
        """AC-4: The retrieve() call in session_lifecycle._build_prompts()
        passes session_id=self._node_id."""
        import ast
        from pathlib import Path

        lifecycle_path = (
            Path(__file__).parents[3] / "agent_fox" / "engine" / "session_lifecycle.py"
        )
        source = lifecycle_path.read_text()

        # Find the retrieve() call and confirm session_id kwarg is present
        assert "session_id=self._node_id" in source, (
            "session_lifecycle.py must pass session_id=self._node_id to retrieve()"
        )

    def test_ac4_protocol_signature_includes_session_id(self) -> None:
        """AC-4: KnowledgeProvider.retrieve() protocol signature includes
        session_id: str | None = None."""
        import inspect

        from agent_fox.knowledge.provider import KnowledgeProvider

        sig = inspect.signature(KnowledgeProvider.retrieve)
        assert "session_id" in sig.parameters, (
            "KnowledgeProvider.retrieve() must have a session_id parameter"
        )
        param = sig.parameters["session_id"]
        assert param.default is None, (
            "session_id parameter must default to None for backward compatibility"
        )


# ===========================================================================
# Integration: end-to-end S1 → complete → S2 does not see finding
# ===========================================================================


class TestEndToEndDeduplication:
    """End-to-end: S1 injects F1, completes → S2 does not see F1.

    Requirements: 558-AC-1, 558-AC-2
    """

    def test_s2_does_not_see_finding_addressed_by_s1(
        self, provider_db, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """After S1 completes successfully and supersedes F1, S2's retrieve()
        does not return any [REVIEW] items for that finding."""
        finding = _make_finding("myspec", task_group="1", description="critical-auth-flaw")
        insert_findings(conn, [finding])

        provider = _make_provider(provider_db)

        # S1 retrieves and is injected with F1
        s1_result = provider.retrieve("myspec", "", task_group="1", session_id="myspec:1:coder")
        assert any("critical-auth-flaw" in item for item in s1_result), (
            "S1 must receive F1"
        )

        # S1 completes successfully
        provider.ingest(
            "myspec:1:coder",
            "myspec",
            {"session_status": "completed", "touched_files": [], "project_root": ""},
        )

        # S2 (a different session, e.g. a subsequent task group) must not see F1
        s2_result = provider.retrieve("myspec", "", task_group="1", session_id="myspec:2:coder")
        assert not any("critical-auth-flaw" in item for item in s2_result), (
            f"S2 must not see a finding that S1 already addressed, but got: {s2_result}"
        )

    def test_only_injected_findings_are_superseded(
        self, provider_db, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Findings injected into S1 are superseded; findings that arrived later
        (after S1's retrieve()) are still active for S2."""
        # F1 exists before S1's retrieve
        f1 = _make_finding("spec", task_group="tg1", description="older-finding")
        insert_findings(conn, [f1])

        provider = _make_provider(provider_db)
        provider.retrieve("spec", "", task_group="tg1", session_id="spec:1:coder")

        # S1 completes — F1 is superseded
        provider.ingest(
            "spec:1:coder",
            "spec",
            {"session_status": "completed", "touched_files": [], "project_root": ""},
        )

        # Now a new reviewer session writes F2 (discovered after S1 completed)
        # We simulate this by inserting a finding for a DIFFERENT task_group
        # (since same tg would get superseded by the reviewer session's insert)
        f2 = _make_finding("spec", task_group="tg2", description="newer-finding")
        insert_findings(conn, [f2])

        s2_result = provider.retrieve("spec", "", session_id="spec:2:coder")
        # F1 should be gone, F2 should be present
        assert not any("older-finding" in item for item in s2_result), (
            "F1 addressed by S1 must not appear in S2"
        )
        assert any("newer-finding" in item for item in s2_result), (
            "F2 (not injected into S1) must appear in S2"
        )


# ===========================================================================
# record_finding_injections and supersede_injected_findings unit tests
# ===========================================================================


class TestRecordFindingInjections:
    """Unit tests for record_finding_injections()."""

    def test_records_ids_in_table(self, conn: duckdb.DuckDBPyConnection) -> None:
        finding_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        record_finding_injections(conn, finding_ids, "sess-1")

        rows = conn.execute(
            "SELECT finding_id FROM finding_injections WHERE session_id = 'sess-1'"
        ).fetchall()
        stored = {row[0] for row in rows}
        assert stored == set(finding_ids)

    def test_empty_list_is_no_op(self, conn: duckdb.DuckDBPyConnection) -> None:
        record_finding_injections(conn, [], "sess-1")
        count = conn.execute("SELECT COUNT(*) FROM finding_injections").fetchone()[0]
        assert count == 0

    def test_duplicate_insert_is_idempotent(self, conn: duckdb.DuckDBPyConnection) -> None:
        finding_id = str(uuid.uuid4())
        record_finding_injections(conn, [finding_id], "sess-1")
        record_finding_injections(conn, [finding_id], "sess-1")  # second call
        count = conn.execute(
            "SELECT COUNT(*) FROM finding_injections WHERE session_id = 'sess-1'"
        ).fetchone()[0]
        assert count == 1, "Duplicate insert must be silently ignored"


class TestSupersededInjectedFindings:
    """Unit tests for supersede_injected_findings()."""

    def test_supersedes_review_findings(self, conn: duckdb.DuckDBPyConnection) -> None:
        finding = _make_finding("S", task_group="1")
        insert_findings(conn, [finding])
        record_finding_injections(conn, [finding.id], "coder-session")
        supersede_injected_findings(conn, "coder-session")

        row = conn.execute(
            "SELECT superseded_by::VARCHAR FROM review_findings WHERE id::VARCHAR = ?",
            [finding.id],
        ).fetchone()
        assert row is not None and row[0] == "coder-session"

    def test_supersedes_verification_results(self, conn: duckdb.DuckDBPyConnection) -> None:
        verdict = _make_verdict("S", task_group="1")
        insert_verdicts(conn, [verdict])
        record_finding_injections(conn, [verdict.id], "coder-session")
        supersede_injected_findings(conn, "coder-session")

        row = conn.execute(
            "SELECT superseded_by::VARCHAR FROM verification_results WHERE id::VARCHAR = ?",
            [verdict.id],
        ).fetchone()
        assert row is not None and row[0] == "coder-session"

    def test_no_op_when_no_injections_recorded(self, conn: duckdb.DuckDBPyConnection) -> None:
        """supersede_injected_findings() with no prior injections is a no-op."""
        finding = _make_finding("S", task_group="1")
        insert_findings(conn, [finding])
        # No record_finding_injections() call
        supersede_injected_findings(conn, "unknown-session")

        active = query_active_findings(conn, "S")
        assert len(active) == 1, "Finding should remain active if not injected"

    def test_does_not_supersede_already_superseded(
        self, conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Already-superseded findings are not touched again."""
        finding = _make_finding("S", task_group="1")
        insert_findings(conn, [finding])
        # Manually supersede it
        conn.execute(
            "UPDATE review_findings SET superseded_by = 'old-session' WHERE id::VARCHAR = ?",
            [finding.id],
        )
        # Record injection and supersede
        record_finding_injections(conn, [finding.id], "coder-session")
        supersede_injected_findings(conn, "coder-session")

        row = conn.execute(
            "SELECT superseded_by::VARCHAR FROM review_findings WHERE id::VARCHAR = ?",
            [finding.id],
        ).fetchone()
        # Should still be the original superseder, not overwritten
        assert row[0] == "old-session", (
            "Already-superseded finding must not be re-superseded"
        )
