"""Integration smoke tests for knowledge retrieval fixes.

Exercises real FoxKnowledgeProvider against real DuckDB (not mocked) to
verify end-to-end flows for summary injection, pre-review finding
elevation, and cross-run carry-forward.

Test Spec: TS-120-SMOKE-1, TS-120-SMOKE-2, TS-120-SMOKE-3
Requirements: 120-REQ-1.2, 120-REQ-1.4, 120-REQ-2.1, 120-REQ-2.2,
              120-REQ-2.3, 120-REQ-4.1, 120-REQ-4.2, 120-REQ-4.4
"""

from __future__ import annotations

import uuid

import duckdb

from agent_fox.core.config import KnowledgeProviderConfig
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
from agent_fox.knowledge.migrations import run_migrations

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conn() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB with all migrations applied."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    return conn


def _make_provider(
    conn: duckdb.DuckDBPyConnection,
    run_id: str | None = None,
) -> FoxKnowledgeProvider:
    """Build a real FoxKnowledgeProvider backed by *conn*."""
    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = conn
    provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())
    if run_id is not None:
        provider.set_run_id(run_id)
    return provider


def _insert_finding_direct(
    conn: duckdb.DuckDBPyConnection,
    *,
    finding_id: str | None = None,
    spec_name: str = "test_spec",
    task_group: str = "1",
    severity: str = "critical",
    description: str = "Test issue",
    session_id: str = "prior_session",
    category: str | None = None,
    superseded_by: str | None = None,
) -> str:
    """Insert a finding directly into review_findings."""
    fid = finding_id or str(uuid.uuid4())
    conn.execute(
        "INSERT INTO review_findings "
        "(id, severity, description, requirement_ref, spec_name, task_group, "
        "session_id, category, created_at, superseded_by) "
        "VALUES (?, ?, ?, NULL, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)",
        [fid, severity, description, spec_name, task_group, session_id,
         category, superseded_by],
    )
    return fid


def _create_run(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    plan_hash: str = "hash1",
) -> None:
    from agent_fox.engine.state import create_run

    create_run(conn, run_id, plan_hash)


def _complete_run(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    status: str = "stalled",
) -> None:
    from agent_fox.engine.state import complete_run

    complete_run(conn, run_id, status)


# ---------------------------------------------------------------------------
# TS-120-SMOKE-1: End-to-End Summary Flow
# ---------------------------------------------------------------------------


class TestSmokeSummaryFlow:
    """Summaries stored via ingest() are retrieved by the next task group.

    Must NOT satisfy with mocked _query_same_spec_summaries -- must hit
    the real database.

    Execution Path: Path 1 from design.md
    Requirements: 120-REQ-1.2, 120-REQ-1.4
    """

    def test_ingest_then_retrieve_context(self) -> None:
        """Store a summary via ingest(), then retrieve() for next group."""
        conn = _make_conn()
        try:
            provider = _make_provider(conn, run_id="test_run")

            # Simulate session completion
            provider.ingest("spec:1", "test_spec", {
                "session_status": "completed",
                "summary": "Built the auth module",
                "archetype": "coder",
                "task_group": "1",
                "attempt": 1,
                "run_id": "test_run",
                "touched_files": [],
                "commit_sha": "abc123",
            })

            # Retrieve for next group
            result = provider.retrieve("test_spec", "test", task_group="2")
            context_items = [
                item for item in result if "[CONTEXT]" in item
            ]
            assert len(context_items) >= 1
            assert any(
                "Built the auth module" in item for item in context_items
            ), f"Expected summary text in context items: {context_items}"
        finally:
            conn.close()

    def test_reviewer_summary_round_trip(self) -> None:
        """Reviewer summary stored via ingest() is retrievable."""
        conn = _make_conn()
        try:
            provider = _make_provider(conn, run_id="test_run")

            provider.ingest("spec:1", "test_spec", {
                "session_status": "completed",
                "summary": "Reviewer found 2 critical issues",
                "archetype": "reviewer",
                "task_group": "1",
                "attempt": 1,
                "run_id": "test_run",
                "touched_files": [],
                "commit_sha": "abc123",
            })

            result = provider.retrieve("test_spec", "test", task_group="2")
            context_items = [
                item for item in result if "[CONTEXT]" in item
            ]
            assert any(
                "Reviewer found 2 critical issues" in item
                for item in context_items
            )
            # Verify archetype is included in the prefix (120-REQ-3.4)
            assert any("reviewer" in item for item in context_items)
        finally:
            conn.close()

    def test_cross_spec_summary_round_trip(self) -> None:
        """Summary from another spec appears as [CROSS-SPEC] item."""
        conn = _make_conn()
        try:
            provider = _make_provider(conn, run_id="test_run")

            provider.ingest("spec_b:2", "spec_b", {
                "session_status": "completed",
                "summary": "Changed auth config",
                "archetype": "coder",
                "task_group": "2",
                "attempt": 1,
                "run_id": "test_run",
                "touched_files": [],
                "commit_sha": "def456",
            })

            result = provider.retrieve("spec_a", "test", task_group="1")
            cross_items = [
                item for item in result if "[CROSS-SPEC]" in item
            ]
            assert any(
                "Changed auth config" in item for item in cross_items
            ), f"Expected cross-spec summary: {cross_items}"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-120-SMOKE-2: Pre-Review to Coder Flow
# ---------------------------------------------------------------------------


class TestSmokePreReviewToCoderFlow:
    """Pre-review findings appear as tracked [REVIEW] items (not
    [CROSS-GROUP]) in the first coder session.

    Must NOT satisfy with mocked _query_reviews or
    _query_cross_group_reviews.

    Execution Path: Path 2 from design.md
    Requirements: 120-REQ-2.1, 120-REQ-2.2, 120-REQ-2.3
    """

    def test_prereview_findings_tracked_not_cross_group(self) -> None:
        """Group 0 findings in [REVIEW], tracked in finding_injections,
        absent from [CROSS-GROUP]."""
        conn = _make_conn()
        try:
            provider = _make_provider(conn)

            prereview_finding_id = str(uuid.uuid4())
            finding_id = _insert_finding_direct(
                conn,
                finding_id=prereview_finding_id,
                spec_name="s",
                task_group="0",
                severity="critical",
                description="Bad design",
                session_id="prereview_session",
            )

            result = provider.retrieve(
                "s", "test", task_group="1", session_id="sess-1",
            )

            # Group 0 finding should be in [REVIEW] results
            review_items = [i for i in result if "[REVIEW]" in i]
            assert any(
                "Bad design" in i for i in review_items
            ), f"Group 0 finding not in review items: {review_items}"

            # Group 0 finding should NOT be in [CROSS-GROUP] results
            cross_group_items = [i for i in result if "[CROSS-GROUP]" in i]
            assert not any(
                "Bad design" in i for i in cross_group_items
            ), f"Group 0 finding leaked into cross-group: {cross_group_items}"

            # Finding ID should be recorded in finding_injections
            injections = conn.execute(
                "SELECT * FROM finding_injections WHERE finding_id = ?",
                [finding_id],
            ).fetchall()
            assert len(injections) == 1, (
                f"Expected 1 injection record, got {len(injections)}"
            )
        finally:
            conn.close()

    def test_prereview_and_same_group_both_in_review(self) -> None:
        """Both group 0 and same-group findings appear in [REVIEW]."""
        conn = _make_conn()
        try:
            provider = _make_provider(conn)

            _insert_finding_direct(
                conn,
                spec_name="s",
                task_group="0",
                severity="critical",
                description="Design flaw from pre-review",
            )
            _insert_finding_direct(
                conn,
                spec_name="s",
                task_group="1",
                severity="major",
                description="Implementation bug",
            )

            result = provider.retrieve("s", "test", task_group="1")
            review_items = [i for i in result if "[REVIEW]" in i]

            assert any(
                "Design flaw from pre-review" in i for i in review_items
            )
            assert any(
                "Implementation bug" in i for i in review_items
            )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-120-SMOKE-3: Cross-Run Carry-Forward Flow
# ---------------------------------------------------------------------------


class TestSmokeCrossRunCarryForward:
    """Unresolved findings from a prior run appear as [PRIOR-RUN] items
    in the new run, without being tracked in finding_injections.

    Must NOT satisfy with mocked _query_prior_run_findings.

    Execution Path: Path 4 from design.md
    Requirements: 120-REQ-4.1, 120-REQ-4.2, 120-REQ-4.4
    """

    def test_prior_run_findings_surfaced(self) -> None:
        """Active findings from a completed prior run appear as
        [PRIOR-RUN] items and are NOT tracked in finding_injections."""
        conn = _make_conn()
        try:
            # Create prior run
            _create_run(conn, "old_run", "hash1")
            _complete_run(conn, "old_run", "stalled")

            # Insert finding during the prior run
            old_finding_id = str(uuid.uuid4())
            finding_id = _insert_finding_direct(
                conn,
                finding_id=old_finding_id,
                spec_name="s",
                task_group="1",
                severity="critical",
                description="Old issue",
                session_id="old_sess",
            )

            # Create current run
            _create_run(conn, "new_run", "hash2")

            provider = _make_provider(conn, run_id="new_run")
            result = provider.retrieve(
                "s", "test", task_group="1", session_id="new_sess",
            )

            # [PRIOR-RUN] item should be present
            prior_items = [i for i in result if "[PRIOR-RUN]" in i]
            assert any(
                "Old issue" in i for i in prior_items
            ), f"Prior-run finding not found: {prior_items}"

            # Finding ID should NOT be in finding_injections
            injections = conn.execute(
                "SELECT * FROM finding_injections WHERE finding_id = ?",
                [finding_id],
            ).fetchall()
            assert len(injections) == 0, (
                f"Prior-run finding should not be tracked: {injections}"
            )
        finally:
            conn.close()

    def test_superseded_prior_findings_not_surfaced(self) -> None:
        """Superseded findings from prior runs do not appear."""
        conn = _make_conn()
        try:
            _create_run(conn, "old_run", "hash1")
            _complete_run(conn, "old_run", "stalled")

            _insert_finding_direct(
                conn,
                spec_name="s",
                task_group="1",
                severity="critical",
                description="Resolved issue",
                session_id="old_sess",
                superseded_by="resolved",
            )

            _create_run(conn, "new_run", "hash2")

            provider = _make_provider(conn, run_id="new_run")
            result = provider.retrieve("s", "test", task_group="1")

            prior_items = [i for i in result if "[PRIOR-RUN]" in i]
            assert not any(
                "Resolved issue" in i for i in prior_items
            ), "Superseded finding should not appear in prior-run items"
        finally:
            conn.close()

    def test_prior_run_fail_verdicts_surfaced(self) -> None:
        """Active FAIL verdicts from prior runs appear as [PRIOR-RUN]
        items (120-REQ-4.5)."""
        conn = _make_conn()
        try:
            _create_run(conn, "old_run", "hash1")
            _complete_run(conn, "old_run", "stalled")

            # Insert a FAIL verdict during the prior run
            verdict_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO verification_results "
                "(id, requirement_id, verdict, evidence, spec_name, task_group, "
                "session_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                [verdict_id, "REQ-5.E3", "FAIL", "Assertion failed",
                 "s", "1", "old_sess"],
            )

            _create_run(conn, "new_run", "hash2")

            provider = _make_provider(conn, run_id="new_run")
            result = provider.retrieve(
                "s", "test", task_group="1", session_id="new_sess",
            )

            prior_items = [i for i in result if "[PRIOR-RUN]" in i]
            assert any(
                "REQ-5.E3" in i for i in prior_items
            ), f"Prior-run FAIL verdict not found: {prior_items}"

            # Verdict should NOT be tracked in finding_injections
            injections = conn.execute(
                "SELECT * FROM finding_injections WHERE finding_id = ?",
                [verdict_id],
            ).fetchall()
            assert len(injections) == 0
        finally:
            conn.close()
