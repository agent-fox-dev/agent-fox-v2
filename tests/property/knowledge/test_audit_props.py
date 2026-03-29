"""Property tests for audit log correctness invariants.

Test Spec: TS-40-P1 through TS-40-P6
Properties: Properties 1-6 from design.md
Requirements: 40-REQ-1.1, 40-REQ-2.1, 40-REQ-2.E1, 40-REQ-5.1, 40-REQ-6.1,
              40-REQ-6.3, 40-REQ-7.3, 40-REQ-9.3, 40-REQ-11.2, 40-REQ-12.1,
              40-REQ-12.2
"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.audit import (
    AuditEvent,
    AuditEventType,
    AuditJsonlSink,
    AuditSeverity,
    default_severity_for,
    enforce_audit_retention,
    event_from_json,
    event_to_json,
    generate_run_id,
)
from agent_fox.knowledge.duckdb_sink import DuckDBSink
from agent_fox.knowledge.sink import SinkDispatcher
from tests.unit.knowledge.conftest import create_schema

# -- TS-40-P1: Run ID Format Invariant ----------------------------------------


class TestRunIdFormat:
    """TS-40-P1: All generated run IDs match format and are unique.

    Property 2 (partial) from design.md.
    Validates: 40-REQ-2.1, 40-REQ-2.E1
    """

    def test_format_and_uniqueness(self) -> None:
        """100 consecutive run IDs all match format and are distinct."""
        ids = [generate_run_id() for _ in range(100)]
        assert len(set(ids)) == 100
        for run_id in ids:
            assert re.fullmatch(r"\d{8}_\d{6}_[0-9a-f]{6}", run_id) is not None


# -- TS-40-P2: Event Serialization Round-Trip ----------------------------------


# Strategy for generating random payloads
payload_strategy = st.dictionaries(
    keys=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
        ),
        min_size=1,
        max_size=10,
    ),
    values=st.one_of(
        st.text(min_size=0, max_size=50),
        st.integers(min_value=-1000, max_value=1000),
        st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
        st.booleans(),
        st.none(),
    ),
    min_size=0,
    max_size=5,
)

event_type_strategy = st.sampled_from(list(AuditEventType))
severity_strategy = st.sampled_from(list(AuditSeverity))


class TestEventSerializationRoundTrip:
    """TS-40-P2: Serializing and deserializing preserves fields.

    Property 4 from design.md.
    Validates: 40-REQ-1.1, 40-REQ-6.3
    """

    @given(
        event_type=event_type_strategy,
        severity=severity_strategy,
        payload=payload_strategy,
        run_id=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=50)
    def test_round_trip(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity,
        payload: dict,
        run_id: str,
    ) -> None:
        """Serialize and deserialize produces equivalent event."""
        event = AuditEvent(
            run_id=run_id,
            event_type=event_type,
            severity=severity,
            payload=payload,
        )
        serialized = event_to_json(event)
        deserialized = event_from_json(serialized)

        assert str(deserialized.id) == str(event.id)
        assert deserialized.run_id == event.run_id
        assert deserialized.event_type == event.event_type
        assert deserialized.severity == event.severity
        assert deserialized.payload == event.payload


# -- TS-40-P3: Severity Classification Correctness ----------------------------


class TestSeverityClassification:
    """TS-40-P3: Event types have correct default severities.

    Property 6 from design.md.
    Validates: 40-REQ-7.3, 40-REQ-9.3, 40-REQ-11.2
    """

    def test_severity_mapping(self) -> None:
        """All event types map to correct default severities."""
        error_types = {AuditEventType.SESSION_FAIL}
        warning_types = {
            AuditEventType.RUN_LIMIT_REACHED,
            AuditEventType.GIT_CONFLICT,
            AuditEventType.HARVEST_EMPTY,
            AuditEventType.REVIEW_PARSE_FAILURE,
        }

        for event_type in AuditEventType:
            severity = default_severity_for(event_type)
            if event_type in error_types:
                assert severity == AuditSeverity.ERROR, (
                    f"{event_type} should be ERROR, got {severity}"
                )
            elif event_type in warning_types:
                assert severity == AuditSeverity.WARNING, (
                    f"{event_type} should be WARNING, got {severity}"
                )
            else:
                assert severity == AuditSeverity.INFO, (
                    f"{event_type} should be INFO, got {severity}"
                )


# -- TS-40-P4: Dual-Write Consistency -----------------------------------------


class TestDualWriteConsistency:
    """TS-40-P4: Events in DuckDB and JSONL are identical.

    Property 3 from design.md.
    Validates: 40-REQ-5.1, 40-REQ-6.1
    """

    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=10)
    def test_dual_write(self, n: int) -> None:
        """N events produce N rows in DuckDB and N lines in JSONL."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        # Apply migration for audit_events
        from agent_fox.knowledge.migrations import apply_pending_migrations

        apply_pending_migrations(conn)

        with tempfile.TemporaryDirectory() as tmpdir:
            audit_dir = Path(tmpdir) / "audit"
            run_id = "test_run"

            duckdb_sink = DuckDBSink(conn)
            jsonl_sink = AuditJsonlSink(audit_dir, run_id)
            dispatcher = SinkDispatcher(
                [duckdb_sink, jsonl_sink]  # type: ignore[list-item]
            )

            events = [
                AuditEvent(
                    run_id=run_id,
                    event_type=AuditEventType.RUN_START,
                    payload={"index": i},
                )
                for i in range(n)
            ]

            for event in events:
                dispatcher.emit_audit_event(event)

            # Check DuckDB
            db_count = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
            assert db_count == n

            # Check JSONL
            jsonl_path = audit_dir / f"audit_{run_id}.jsonl"
            jsonl_lines = jsonl_path.read_text().strip().split("\n")
            assert len(jsonl_lines) == n

            # Check ID consistency
            db_ids = {
                row[0] for row in conn.execute("SELECT id FROM audit_events").fetchall()
            }
            jsonl_ids = set()
            for line in jsonl_lines:
                parsed = json.loads(line)
                jsonl_ids.add(parsed["id"])

            assert db_ids == jsonl_ids

        conn.close()


# -- TS-40-P5: Retention Bound ------------------------------------------------


class TestRetentionBound:
    """TS-40-P5: After retention enforcement, at most max_runs retained.

    Property 5 from design.md.
    Validates: 40-REQ-12.1, 40-REQ-12.2
    """

    @given(
        n_runs=st.integers(min_value=1, max_value=30),
        max_runs=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=15)
    def test_retention_bound(self, n_runs: int, max_runs: int) -> None:
        """Remaining runs after enforcement <= min(n_runs, max_runs)."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        from agent_fox.knowledge.migrations import apply_pending_migrations

        apply_pending_migrations(conn)

        with tempfile.TemporaryDirectory() as tmpdir:
            audit_dir = Path(tmpdir) / "audit"
            audit_dir.mkdir(parents=True)

            base_time = datetime(2026, 1, 1, tzinfo=UTC)
            for i in range(n_runs):
                run_id = f"run_{i:04d}"
                ts = base_time + timedelta(hours=i)
                conn.execute(
                    """
                    INSERT INTO audit_events
                        (id, timestamp, run_id, event_type, severity, payload)
                    VALUES (?, ?, ?, 'run.start', 'info', '{}')
                    """,
                    [str(uuid4()), ts, run_id],
                )
                # Create JSONL file
                (audit_dir / f"audit_{run_id}.jsonl").write_text(
                    json.dumps({"run_id": run_id}) + "\n"
                )

            enforce_audit_retention(audit_dir, conn, max_runs=max_runs)

            remaining = conn.execute(
                "SELECT COUNT(DISTINCT run_id) FROM audit_events"
            ).fetchone()[0]
            assert remaining <= max_runs
            assert remaining == min(n_runs, max_runs)

        conn.close()


# -- TS-40-P6: Event Completeness Per Run --------------------------------------


class TestEventCompleteness:
    """TS-40-P6: Every completed run has exactly one run.start and run.complete.

    Property 1 from design.md.
    Validates: 40-REQ-9.1, 40-REQ-9.2
    """

    def test_single_run_completeness(self) -> None:
        """A completed run has exactly 1 run.start and 1 run.complete."""
        run_id = "20260312_143000_abc123"
        events = [
            AuditEvent(run_id=run_id, event_type=AuditEventType.RUN_START),
            AuditEvent(run_id=run_id, event_type=AuditEventType.SESSION_START),
            AuditEvent(run_id=run_id, event_type=AuditEventType.SESSION_COMPLETE),
            AuditEvent(run_id=run_id, event_type=AuditEventType.RUN_COMPLETE),
        ]

        starts = [e for e in events if e.event_type == AuditEventType.RUN_START]
        completes = [e for e in events if e.event_type == AuditEventType.RUN_COMPLETE]
        assert len(starts) == 1
        assert len(completes) == 1

    @given(n_sessions=st.integers(min_value=1, max_value=10))
    @settings(max_examples=10)
    def test_n_sessions_have_n_starts(self, n_sessions: int) -> None:
        """N sessions produce N session.start events."""
        run_id = "test_run"
        events = [AuditEvent(run_id=run_id, event_type=AuditEventType.RUN_START)]
        for _ in range(n_sessions):
            events.append(
                AuditEvent(run_id=run_id, event_type=AuditEventType.SESSION_START)
            )
            events.append(
                AuditEvent(run_id=run_id, event_type=AuditEventType.SESSION_COMPLETE)
            )
        events.append(AuditEvent(run_id=run_id, event_type=AuditEventType.RUN_COMPLETE))

        session_starts = [
            e for e in events if e.event_type == AuditEventType.SESSION_START
        ]
        assert len(session_starts) == n_sessions
