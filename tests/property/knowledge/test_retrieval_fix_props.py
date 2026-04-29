"""Property tests for knowledge retrieval fixes.

Validates key invariants across randomized inputs:
- TS-120-P1: run_id gating (summaries empty iff run_id is falsy)
- TS-120-P2: no duplication between REVIEW and CROSS-GROUP
- TS-120-P3: prior-run findings never tracked in finding_injections
- TS-120-P4: generate_archetype_summary always returns non-empty string

Test Spec: TS-120-P1, TS-120-P2, TS-120-P3, TS-120-P4
Requirements: 120-REQ-1.1, 120-REQ-1.2, 120-REQ-1.E1, 120-REQ-1.E2,
              120-REQ-2.1, 120-REQ-2.3,
              120-REQ-3.1, 120-REQ-3.2, 120-REQ-3.E1, 120-REQ-3.E2,
              120-REQ-4.4
"""

from __future__ import annotations

import uuid

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import KnowledgeProviderConfig
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
from agent_fox.knowledge.migrations import run_migrations
from agent_fox.knowledge.review_store import ReviewFinding, VerificationResult
from agent_fox.knowledge.summary_store import SummaryRecord, insert_summary


def _generate_archetype_summary(*args, **kwargs):
    """Deferred import of generate_archetype_summary (not yet implemented)."""
    from agent_fox.knowledge.fox_provider import generate_archetype_summary

    return generate_archetype_summary(*args, **kwargs)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _fresh_db() -> tuple[duckdb.DuckDBPyConnection, KnowledgeDB]:
    """Create a fresh in-memory DuckDB with full schema and KnowledgeDB wrapper."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = conn
    return conn, db


def _insert_finding_direct(
    conn: duckdb.DuckDBPyConnection,
    *,
    finding_id: str | None = None,
    spec_name: str = "test_spec",
    task_group: str = "1",
    severity: str = "critical",
    description: str = "Test issue",
    session_id: str = "s1",
) -> str:
    fid = finding_id or str(uuid.uuid4())
    conn.execute(
        "INSERT INTO review_findings "
        "(id, severity, description, requirement_ref, spec_name, task_group, "
        "session_id, category, created_at) "
        "VALUES (?, ?, ?, NULL, ?, ?, ?, NULL, CURRENT_TIMESTAMP)",
        [fid, severity, description, spec_name, task_group, session_id],
    )
    return fid


# ---------------------------------------------------------------------------
# TS-120-P1: run_id Gating
# ---------------------------------------------------------------------------


class TestRunIdGating:
    """Summary queries return empty iff run_id is not set or empty.

    Property 1: For any run_id in {None, "", "valid_run_id"}, when run_id
    is falsy summary queries return empty. When truthy and matching
    summaries exist, queries return non-empty.

    Requirements: 120-REQ-1.1, 120-REQ-1.2, 120-REQ-1.E1, 120-REQ-1.E2
    """

    @given(
        run_id_choice=st.sampled_from([None, "", "valid_run_id"]),
    )
    @settings(max_examples=3)
    def test_run_id_gating(self, run_id_choice: str | None) -> None:
        conn, db = _fresh_db()
        try:
            provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())
            if run_id_choice is not None:
                provider.set_run_id(run_id_choice)

            # Insert a summary matching the "valid" run_id
            insert_summary(
                conn,
                SummaryRecord(
                    id=str(uuid.uuid4()),
                    node_id="test_spec:1",
                    run_id="valid_run_id",
                    spec_name="test_spec",
                    task_group="1",
                    archetype="coder",
                    attempt=1,
                    summary="Test summary",
                    created_at="2026-04-29T10:00:00",
                ),
            )

            result = provider.retrieve("test_spec", "test", task_group="2")
            context_items = [i for i in result if "[CONTEXT]" in i]

            if not run_id_choice:  # None or ""
                assert context_items == []
            else:
                assert len(context_items) > 0
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-120-P2: No Duplication Between Review and Cross-Group
# ---------------------------------------------------------------------------


class TestNoDuplicationReviewCrossGroup:
    """A finding never appears in both [REVIEW] and [CROSS-GROUP].

    Property 7: For any set of findings with random task_groups including
    "0", for any target_group T, the set of finding descriptions in REVIEW
    items and the set in CROSS-GROUP items are disjoint.

    Requirements: 120-REQ-2.1, 120-REQ-2.3
    """

    @given(
        target_group=st.sampled_from(["1", "2", "3"]),
        # Generate 1-8 findings across groups 0,1,2,3
        finding_groups=st.lists(
            st.sampled_from(["0", "1", "2", "3"]),
            min_size=1,
            max_size=8,
        ),
    )
    @settings(max_examples=20)
    def test_disjoint_review_and_cross_group(
        self, target_group: str, finding_groups: list[str]
    ) -> None:
        conn, db = _fresh_db()
        try:
            provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())

            for i, group in enumerate(finding_groups):
                _insert_finding_direct(
                    conn,
                    spec_name="test_spec",
                    task_group=group,
                    severity="critical",
                    description=f"Finding_{i}_group_{group}",
                    session_id=f"s_{i}",
                )

            result = provider.retrieve("test_spec", "test desc", task_group=target_group)

            # Extract descriptions from [REVIEW] and [CROSS-GROUP] items
            review_descs: set[str] = set()
            cross_descs: set[str] = set()
            for item in result:
                if "[REVIEW]" in item:
                    # Extract the description portion
                    for i, group in enumerate(finding_groups):
                        desc = f"Finding_{i}_group_{group}"
                        if desc in item:
                            review_descs.add(desc)
                if "[CROSS-GROUP]" in item:
                    for i, group in enumerate(finding_groups):
                        desc = f"Finding_{i}_group_{group}"
                        if desc in item:
                            cross_descs.add(desc)

            assert review_descs.isdisjoint(cross_descs), (
                f"Overlap between REVIEW and CROSS-GROUP: {review_descs & cross_descs}"
            )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-120-P3: Prior-Run Findings Never Tracked
# ---------------------------------------------------------------------------


class TestPriorRunFindingsNeverTracked:
    """Prior-run finding IDs never appear in finding_injections.

    Property 6: After retrieve(), finding_injections contains no prior-run IDs.

    Requirements: 120-REQ-4.4
    """

    @given(
        num_prior_findings=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=5)
    def test_prior_run_ids_not_tracked(self, num_prior_findings: int) -> None:
        conn, db = _fresh_db()
        try:
            from agent_fox.engine.state import complete_run, create_run

            # Create and complete a prior run
            create_run(conn, "prior_run", "hash_prior")
            complete_run(conn, "prior_run", "stalled")

            prior_ids: set[str] = set()
            for i in range(num_prior_findings):
                fid = _insert_finding_direct(
                    conn,
                    spec_name="test_spec",
                    severity="critical",
                    description=f"Prior finding {i}",
                    session_id="prior_session",
                )
                prior_ids.add(fid)

            # Create current run
            create_run(conn, "current_run", "hash_current")

            provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())
            provider.set_run_id("current_run")
            provider.retrieve("test_spec", "test", task_group="1", session_id="sess-1")

            injected = conn.execute(
                "SELECT finding_id FROM finding_injections"
            ).fetchall()
            injected_ids = {row[0] for row in injected}

            assert prior_ids.isdisjoint(injected_ids), (
                f"Prior-run IDs leaked into finding_injections: {prior_ids & injected_ids}"
            )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-120-P4: Archetype Summary Completeness
# ---------------------------------------------------------------------------


class TestArchetypeSummaryCompleteness:
    """generate_archetype_summary always returns a non-empty string.

    Property 3: For any archetype in {"reviewer", "verifier"}, findings/verdicts
    list of length 0..20, the return value is a non-empty string.

    Requirements: 120-REQ-3.1, 120-REQ-3.2, 120-REQ-3.E1, 120-REQ-3.E2
    """

    @given(
        num_items=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=15)
    def test_reviewer_summary_always_nonempty(self, num_items: int) -> None:
        findings = [
            ReviewFinding(
                id=str(uuid.uuid4()),
                severity="critical" if i % 2 == 0 else "major",
                description=f"Finding {i}",
                requirement_ref=None,
                spec_name="spec",
                task_group="1",
                session_id="s1",
            )
            for i in range(num_items)
        ]
        summary = _generate_archetype_summary("reviewer", findings=findings)
        assert isinstance(summary, str)
        assert len(summary) > 0

    @given(
        num_items=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=15)
    def test_verifier_summary_always_nonempty(self, num_items: int) -> None:
        verdicts = [
            VerificationResult(
                id=str(uuid.uuid4()),
                requirement_id=f"REQ-{i}.1",
                verdict="PASS" if i % 3 != 0 else "FAIL",
                evidence=None,
                spec_name="spec",
                task_group="1",
                session_id="s1",
            )
            for i in range(num_items)
        ]
        summary = _generate_archetype_summary("verifier", verdicts=verdicts)
        assert isinstance(summary, str)
        assert len(summary) > 0
