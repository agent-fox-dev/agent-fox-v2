"""Property-based tests for session summary storage.

Test Spec: TS-119-P1, TS-119-P2, TS-119-P3, TS-119-P4, TS-119-P5, TS-119-P6
Properties: 2, 3, 4, 5, 6, 7 from design.md
"""

from __future__ import annotations

import uuid

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.migrations import run_migrations
from agent_fox.knowledge.summary_store import (
    SummaryRecord,
    insert_summary,
    query_cross_spec_summaries,
    query_same_spec_summaries,
)

_SESSION_SUMMARIES_DDL = """
CREATE TABLE IF NOT EXISTS session_summaries (
    id          UUID PRIMARY KEY,
    node_id     VARCHAR NOT NULL,
    run_id      VARCHAR NOT NULL,
    spec_name   VARCHAR NOT NULL,
    task_group  VARCHAR NOT NULL,
    archetype   VARCHAR NOT NULL,
    attempt     INTEGER NOT NULL DEFAULT 1,
    summary     TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL
);
"""

spec_names = st.sampled_from(["spec_a", "spec_b", "spec_c", "spec_d", "spec_e"])
task_groups = st.integers(min_value=1, max_value=9)
archetypes = st.sampled_from(["coder", "reviewer", "verifier"])
attempts = st.integers(min_value=1, max_value=3)

summary_record_st = st.fixed_dictionaries({
    "spec_name": spec_names,
    "task_group": task_groups,
    "archetype": archetypes,
    "attempt": attempts,
})


def _make_conn_with_table():
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    conn.execute(_SESSION_SUMMARIES_DDL)
    return conn


def _make_record(spec_name, task_group, archetype, attempt,
                 run_id="run-1", created_at=None):
    tg = str(task_group)
    return SummaryRecord(
        id=str(uuid.uuid4()), node_id=f"{spec_name}:{tg}",
        run_id=run_id, spec_name=spec_name, task_group=tg,
        archetype=archetype, attempt=attempt,
        summary=f"Summary for {spec_name} group {tg} attempt {attempt}",
        created_at=created_at or f"2026-04-28T{10 + task_group}:00:00",
    )


# TS-119-P1: Prior-group filtering correctness (Property 2)
class TestPriorGroupFilteringProperty:
    @settings(max_examples=100)
    @given(
        current_group=st.integers(min_value=1, max_value=9),
        current_spec=st.sampled_from(["spec_a", "spec_b", "spec_c"]),
        records=st.lists(summary_record_st, min_size=1, max_size=15),
    )
    def test_prior_group_filtering(self, current_group, current_spec, records):
        conn = _make_conn_with_table()
        try:
            for rec in records:
                insert_summary(conn, _make_record(
                    rec["spec_name"], rec["task_group"],
                    rec["archetype"], rec["attempt"],
                ))
            results = query_same_spec_summaries(conn, current_spec, str(current_group), "run-1")
            for r in results:
                assert r.spec_name == current_spec
                assert int(r.task_group) < current_group
                assert r.archetype == "coder"
            groups = [r.task_group for r in results]
            assert len(groups) == len(set(groups))
            for r in results:
                max_attempt = max(
                    rec["attempt"] for rec in records
                    if rec["spec_name"] == current_spec
                    and rec["task_group"] == int(r.task_group)
                    and rec["archetype"] == "coder"
                )
                assert r.attempt == max_attempt
        finally:
            conn.close()


# TS-119-P2: Cross-spec exclusion (Property 3)
class TestCrossSpecExclusionProperty:
    @settings(max_examples=100)
    @given(
        current_spec=spec_names,
        records=st.lists(summary_record_st, min_size=1, max_size=15),
    )
    def test_cross_spec_exclusion(self, current_spec, records):
        conn = _make_conn_with_table()
        try:
            for rec in records:
                insert_summary(conn, _make_record(
                    rec["spec_name"], rec["task_group"],
                    rec["archetype"], rec["attempt"],
                ))
            results = query_cross_spec_summaries(conn, current_spec, "run-1")
            for r in results:
                assert r.spec_name != current_spec
                assert r.archetype == "coder"
            pairs = [(r.spec_name, r.task_group) for r in results]
            assert len(pairs) == len(set(pairs))
        finally:
            conn.close()


# TS-119-P3: Append-only invariant (Property 4)
class TestAppendOnlyProperty:
    @settings(max_examples=100)
    @given(num_inserts=st.integers(min_value=1, max_value=20))
    def test_append_only(self, num_inserts):
        conn = _make_conn_with_table()
        try:
            records = []
            for i in range(num_inserts):
                rec = _make_record("spec_a", (i % 5) + 1, "coder", (i % 3) + 1)
                records.append(rec)
                insert_summary(conn, rec)
            count = conn.execute("SELECT COUNT(*) FROM session_summaries").fetchone()[0]
            assert count == num_inserts
            for rec in records:
                row = conn.execute(
                    "SELECT summary FROM session_summaries WHERE id = ?::UUID", [rec.id]
                ).fetchone()
                assert row is not None
                assert row[0] == rec.summary
        finally:
            conn.close()


# TS-119-P4: Sort order stability (Property 7)
class TestSortOrderProperty:
    @settings(max_examples=100)
    @given(records=st.lists(summary_record_st, min_size=1, max_size=10))
    def test_sort_order(self, records):
        conn = _make_conn_with_table()
        try:
            for i, rec in enumerate(records):
                insert_summary(conn, _make_record(
                    rec["spec_name"], rec["task_group"],
                    rec["archetype"], rec["attempt"],
                    created_at=f"2026-04-28T{10 + (i % 14):02d}:{i % 60:02d}:00",
                ))
            same = query_same_spec_summaries(conn, "spec_a", "9", "run-1")
            for i in range(1, len(same)):
                assert int(same[i].task_group) > int(same[i - 1].task_group)
            cross = query_cross_spec_summaries(conn, "spec_a", "run-1")
            for i in range(1, len(cross)):
                assert cross[i].created_at <= cross[i - 1].created_at
        finally:
            conn.close()


# TS-119-P5: Graceful degradation (Property 5)
class TestGracefulDegradationProperty:
    @settings(max_examples=100)
    @given(
        spec=spec_names,
        group=task_groups,
        run=st.sampled_from(["run-1", "run-2"]),
    )
    def test_graceful_degradation(self, spec, group, run):
        conn = duckdb.connect(":memory:")
        try:
            result1 = query_same_spec_summaries(conn, spec, str(group), run)
            result2 = query_cross_spec_summaries(conn, spec, run)
            assert result1 == []
            assert result2 == []
        finally:
            conn.close()


# TS-119-P6: Audit payload consistency (Property 6)
class TestAuditPayloadConsistencyProperty:
    @settings(max_examples=50)
    @given(summary_len=st.integers(min_value=0, max_value=5000))
    def test_audit_payload_consistency(self, summary_len):
        """Verify truncate_for_audit produces correct output for any length.

        Exercises the production truncation function rather than reimplementing
        the formula locally.  Fails until truncate_for_audit is implemented.
        """
        from agent_fox.knowledge.summary_store import truncate_for_audit

        summary_text = "x" * summary_len
        audit_summary = truncate_for_audit(summary_text)

        if summary_len > 2000:
            assert len(audit_summary) == 2003
            assert audit_summary.endswith("...")
        else:
            assert audit_summary == summary_text
            assert len(audit_summary) == summary_len
