"""Tests for scope_guard.telemetry module.

Test Spec: TS-87-9, TS-87-15, TS-87-16, TS-87-17, TS-87-19, TS-87-E13,
           TS-87-P15, TS-87-P16, TS-87-P18
Requirements: 87-REQ-2.5, 87-REQ-4.1 through 87-REQ-4.4, 87-REQ-5.1 through 87-REQ-5.3, 87-REQ-5.E1
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import pytest

from agent_fox.scope_guard.models import (
    Deliverable,
    DeliverableCheckResult,
    DeliverableStatus,
    ScopeCheckResult,
    ScopeGuardSessionOutcome,
    SessionClassification,
)
from agent_fox.scope_guard.telemetry import (
    get_session_prompt,
    persist_prompt,
    query_waste_report,
    record_scope_check,
    record_session_outcome,
)

# ---------------------------------------------------------------------------
# TS-87-9: Scope check telemetry logging
# Requirement: 87-REQ-2.5
# ---------------------------------------------------------------------------


class TestScopeCheckTelemetryLogging:
    """TS-87-9: Scope check result is persisted to the telemetry store."""

    @pytest.mark.integration
    def test_scope_check_result_persisted(self, sg_duckdb: duckdb.DuckDBPyConnection) -> None:
        scope_result = ScopeCheckResult(
            task_group_number=2,
            deliverable_results=[
                DeliverableCheckResult(
                    Deliverable("src/foo.rs", "validate", 2),
                    DeliverableStatus.PENDING,
                    "stub body",
                ),
                DeliverableCheckResult(
                    Deliverable("src/bar.rs", "process", 2),
                    DeliverableStatus.ALREADY_IMPLEMENTED,
                    "has implementation",
                ),
            ],
            overall="partially-implemented",
            check_duration_ms=50,
            deliverable_count=2,
        )
        record_scope_check(sg_duckdb, scope_result)
        rows = sg_duckdb.execute(
            "SELECT * FROM scope_check_results WHERE task_group_number = 2"
        ).fetchall()
        assert len(rows) == 1
        # Columns: id, spec_number, task_group_number, overall_status, deliverable_count,
        #          check_duration_ms, deliverable_results, timestamp
        row = rows[0]
        # Check deliverable_count
        assert row[4] == 2
        # Check check_duration_ms > 0
        assert row[5] > 0


# ---------------------------------------------------------------------------
# TS-87-15: Pre-flight skip recorded distinctly from no-op
# Requirement: 87-REQ-4.2
# ---------------------------------------------------------------------------


class TestPreflightSkipDistinctFromNoop:
    """TS-87-15: pre-flight-skip outcome stored with distinct classification."""

    @pytest.mark.integration
    def test_preflight_skip_classification(self, sg_duckdb: duckdb.DuckDBPyConnection) -> None:
        outcome = ScopeGuardSessionOutcome(
            session_id="sess-skip-1",
            spec_number=4,
            task_group_number=5,
            classification=SessionClassification.PRE_FLIGHT_SKIP,
            duration_seconds=0.0,
            cost_dollars=0.0,
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            reason="all deliverables already implemented",
        )
        record_session_outcome(sg_duckdb, outcome)
        rows = sg_duckdb.execute(
            "SELECT classification FROM session_outcomes WHERE session_id = 'sess-skip-1'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "pre-flight-skip"


# ---------------------------------------------------------------------------
# TS-87-16: No-op/pre-flight-skip telemetry fields completeness
# Requirement: 87-REQ-4.3
# ---------------------------------------------------------------------------


class TestNoopRecordFieldCompleteness:
    """TS-87-16: No-op records contain all required fields."""

    @pytest.mark.integration
    def test_all_fields_present(self, sg_duckdb: duckdb.DuckDBPyConnection) -> None:
        outcome = ScopeGuardSessionOutcome(
            session_id="sess-noop-fields",
            spec_number=7,
            task_group_number=2,
            classification=SessionClassification.NO_OP,
            duration_seconds=89.5,
            cost_dollars=3.00,
            timestamp=datetime(2024, 1, 15, 12, 0, 0),
            reason="no-op",
        )
        record_session_outcome(sg_duckdb, outcome)
        rows = sg_duckdb.execute(
            "SELECT spec_number, task_group_number, duration_seconds, cost_dollars, "
            "timestamp, classification FROM session_outcomes WHERE session_id = 'sess-noop-fields'"
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row[0] == 7   # spec_number
        assert row[1] == 2   # task_group_number
        assert row[2] == 89.5  # duration_seconds
        assert row[3] == 3.00  # cost_dollars
        assert row[4] is not None  # timestamp
        assert row[5] == "no-op"  # classification


# ---------------------------------------------------------------------------
# TS-87-17: Aggregate waste report query
# Requirement: 87-REQ-4.4
# ---------------------------------------------------------------------------


class TestAggregateWasteReport:
    """TS-87-17: query_waste_report returns correct per-spec aggregates."""

    @pytest.mark.integration
    def test_waste_report_aggregation(self, sg_duckdb: duckdb.DuckDBPyConnection) -> None:
        # Seed data: Spec 4 — 2 no-ops, 1 pre-flight-skip
        for i in range(2):
            record_session_outcome(
                sg_duckdb,
                ScopeGuardSessionOutcome(
                    session_id=f"sess-noop-4-{i}",
                    spec_number=4,
                    task_group_number=i + 1,
                    classification=SessionClassification.NO_OP,
                    duration_seconds=100.0,
                    cost_dollars=3.50,
                    timestamp=datetime(2024, 1, 15, 10, i, 0),
                ),
            )
        record_session_outcome(
            sg_duckdb,
            ScopeGuardSessionOutcome(
                session_id="sess-skip-4",
                spec_number=4,
                task_group_number=3,
                classification=SessionClassification.PRE_FLIGHT_SKIP,
                duration_seconds=0.0,
                cost_dollars=0.0,
                timestamp=datetime(2024, 1, 15, 10, 5, 0),
            ),
        )
        # Seed data: Spec 7 — 1 no-op
        record_session_outcome(
            sg_duckdb,
            ScopeGuardSessionOutcome(
                session_id="sess-noop-7",
                spec_number=7,
                task_group_number=1,
                classification=SessionClassification.NO_OP,
                duration_seconds=200.0,
                cost_dollars=4.00,
                timestamp=datetime(2024, 1, 15, 11, 0, 0),
            ),
        )

        report = query_waste_report(sg_duckdb, spec_number=None)
        assert len(report.per_spec) == 2

        spec4 = next(s for s in report.per_spec if s.spec_number == 4)
        assert spec4.no_op_count == 2
        assert spec4.pre_flight_skip_count == 1
        assert spec4.total_wasted_cost == 7.00
        assert spec4.total_wasted_duration == 200.0

        spec7 = next(s for s in report.per_spec if s.spec_number == 7)
        assert spec7.no_op_count == 1
        assert spec7.pre_flight_skip_count == 0
        assert spec7.total_wasted_cost == 4.00
        assert spec7.total_wasted_duration == 200.0


# ---------------------------------------------------------------------------
# TS-87-19: Prompt text persisted in telemetry store
# Requirement: 87-REQ-5.2
# ---------------------------------------------------------------------------


class TestPromptPersistedAndRetrievable:
    """TS-87-19: Full prompt text is stored and retrievable."""

    @pytest.mark.integration
    def test_prompt_round_trip(self, sg_duckdb: duckdb.DuckDBPyConnection) -> None:
        prompt_text = (
            "This is a test prompt with <!-- SCOPE_GUARD:STUB_ONLY -->"
            " directive <!-- /SCOPE_GUARD:STUB_ONLY -->"
        )
        persist_prompt(sg_duckdb, "sess-prompt-1", prompt_text)
        record = get_session_prompt(sg_duckdb, "sess-prompt-1")
        assert record is not None
        assert record.session_id == "sess-prompt-1"
        assert "SCOPE_GUARD:STUB_ONLY" in record.prompt_text
        assert record.stub_directive_present is True
        assert record.truncated is False

    @pytest.mark.integration
    def test_prompt_without_directive(self, sg_duckdb: duckdb.DuckDBPyConnection) -> None:
        persist_prompt(sg_duckdb, "sess-prompt-2", "A normal prompt without directive")
        record = get_session_prompt(sg_duckdb, "sess-prompt-2")
        assert record is not None
        assert record.stub_directive_present is False


# ---------------------------------------------------------------------------
# TS-87-E13: Prompt truncation for oversized prompts
# Requirement: 87-REQ-5.E1
# ---------------------------------------------------------------------------


class TestPromptTruncation:
    """TS-87-E13: Prompt exceeding 100K chars is truncated with flag."""

    @pytest.mark.integration
    def test_large_prompt_truncated(self, sg_duckdb: duckdb.DuckDBPyConnection) -> None:
        large_prompt = "A" * 100_001  # exceeds 100K limit
        persist_prompt(sg_duckdb, "sess-large", large_prompt)
        record = get_session_prompt(sg_duckdb, "sess-large")
        assert record is not None
        assert record.truncated is True
        # Should retain first 500 and last 500 chars
        assert len(record.prompt_text) < 100_001
        assert record.prompt_text[:500] == "A" * 500
        assert record.prompt_text[-500:] == "A" * 500
        assert "TRUNCATED" in record.prompt_text


# ---------------------------------------------------------------------------
# TS-87-P15: Property — Telemetry Record Completeness
# Property 15 from design.md
# Validates: 87-REQ-4.3
# ---------------------------------------------------------------------------


class TestPropertyTelemetryCompleteness:
    """TS-87-P15: Required fields present in stored records."""

    @pytest.mark.property
    @pytest.mark.integration
    def test_all_required_fields_present(self, sg_duckdb: duckdb.DuckDBPyConnection) -> None:
        outcome = ScopeGuardSessionOutcome(
            session_id="sess-p15",
            spec_number=3,
            task_group_number=1,
            classification=SessionClassification.NO_OP,
            duration_seconds=55.0,
            cost_dollars=2.00,
            timestamp=datetime(2024, 6, 1, 12, 0, 0),
            reason="no-op",
        )
        record_session_outcome(sg_duckdb, outcome)
        rows = sg_duckdb.execute(
            "SELECT session_id, spec_number, task_group_number, classification, "
            "duration_seconds, cost_dollars, timestamp FROM session_outcomes "
            "WHERE session_id = 'sess-p15'"
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row[0] == "sess-p15"
        assert row[1] == 3
        assert row[2] == 1
        assert row[3] == "no-op"
        assert row[4] == 55.0
        assert row[5] == 2.00
        assert row[6] is not None


# ---------------------------------------------------------------------------
# TS-87-P16: Property — Waste Report Aggregation
# Property 16 from design.md
# Validates: 87-REQ-4.4
# ---------------------------------------------------------------------------


class TestPropertyWasteReportAggregation:
    """TS-87-P16: Aggregation sums match individual records."""

    @pytest.mark.property
    @pytest.mark.integration
    def test_aggregation_sums_correct(self, sg_duckdb: duckdb.DuckDBPyConnection) -> None:
        # Insert 3 no-ops for spec 10
        for i in range(3):
            record_session_outcome(
                sg_duckdb,
                ScopeGuardSessionOutcome(
                    session_id=f"sess-p16-{i}",
                    spec_number=10,
                    task_group_number=i + 1,
                    classification=SessionClassification.NO_OP,
                    duration_seconds=100.0,
                    cost_dollars=2.00,
                    timestamp=datetime(2024, 6, 1, 12, i, 0),
                ),
            )
        report = query_waste_report(sg_duckdb, spec_number=10)
        assert len(report.per_spec) == 1
        spec10 = report.per_spec[0]
        assert spec10.no_op_count == 3
        assert spec10.total_wasted_cost == 6.00
        assert spec10.total_wasted_duration == 300.0


# ---------------------------------------------------------------------------
# TS-87-P18: Property — Prompt Persistence and Audit
# Property 18 from design.md
# Validates: 87-REQ-5.2
# ---------------------------------------------------------------------------


class TestPropertyPromptPersistence:
    """TS-87-P18: Persisted prompt is retrievable with correct metadata."""

    @pytest.mark.property
    @pytest.mark.integration
    def test_persisted_prompt_retrievable(self, sg_duckdb: duckdb.DuckDBPyConnection) -> None:
        prompt = "Test prompt with <!-- SCOPE_GUARD:STUB_ONLY -->content<!-- /SCOPE_GUARD:STUB_ONLY -->"
        persist_prompt(sg_duckdb, "sess-p18", prompt)
        record = get_session_prompt(sg_duckdb, "sess-p18")
        assert record is not None
        assert record.session_id == "sess-p18"
        assert record.stub_directive_present is True
        assert record.truncated is False
        assert record.prompt_text == prompt
