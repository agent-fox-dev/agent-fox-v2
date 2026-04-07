"""Property tests for review archetype output visibility.

Tests invariants for response truncation, audit event counts,
blocking reason ID caps, severity filter monotonicity, findings
table row counts, and status summary omission.

Test Spec: TS-84-P1 through TS-84-P6
Requirements: 84-REQ-1.1, 84-REQ-1.E1, 84-REQ-2.1, 84-REQ-3.1,
              84-REQ-3.E1, 84-REQ-4.1, 84-REQ-4.3, 84-REQ-4.6,
              84-REQ-5.1, 84-REQ-5.2
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.reporting.findings import (
    FindingRow,
    format_findings_table,
    query_findings,
    query_findings_summary,
)
from tests.unit.knowledge.conftest import SCHEMA_DDL

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# TS-84-P1: Text strategy for response truncation
response_text_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="\x00",
    ),
    min_size=0,
    max_size=200_000,
)

SEVERITY_LEVELS = ["critical", "major", "minor", "observation"]
SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2, "observation": 3}


def finding_row_strategy():
    """Strategy for generating FindingRow objects."""
    return st.builds(
        FindingRow,
        id=st.text(min_size=8, max_size=12, alphabet="abcdef0123456789").map(
            lambda s: f"F-{s}"
        ),
        severity=st.sampled_from(SEVERITY_LEVELS),
        archetype=st.sampled_from(["skeptic", "oracle"]),
        spec_name=st.text(
            min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_0123456789"
        ),
        task_group=st.sampled_from(["1", "2", "3"]),
        description=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
                blacklist_characters="\x00\n\r",
            ),
        ),
        created_at=st.just(datetime.now(UTC)),
    )


# ---------------------------------------------------------------------------
# TS-84-P1: Response truncation preserves prefix
# ---------------------------------------------------------------------------


class TestResponseTruncationProperty:
    """TS-84-P1: For any response string, truncation is correct."""

    @given(s=response_text_strategy)
    @settings(max_examples=50)
    def test_truncation_preserves_prefix(self, s: str) -> None:
        """For any string, truncation either preserves it or takes first 100k + marker."""
        from agent_fox.knowledge.jsonl_sink import _truncate_response

        result = _truncate_response(s)
        if len(s) <= 100_000:
            assert result == s
        else:
            assert result == s[:100_000] + "[truncated]"


# ---------------------------------------------------------------------------
# TS-84-P2: Audit event count matches insertion count
# ---------------------------------------------------------------------------


class TestAuditEventCountProperty:
    """TS-84-P2: Audit event count matches insertion count."""

    @given(
        n_findings=st.integers(min_value=1, max_value=10),
        severities=st.lists(
            st.sampled_from(SEVERITY_LEVELS), min_size=1, max_size=10
        ),
    )
    @settings(max_examples=20)
    def test_audit_count_matches_insert_count(
        self, n_findings: int, severities: list[str]
    ) -> None:
        """Audit event count equals number of inserted records."""
        from unittest.mock import MagicMock

        from agent_fox.engine.review_persistence import persist_review_findings
        from agent_fox.knowledge.audit import AuditEventType

        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)

        mock_sink = MagicMock()
        findings_json = json.dumps(
            [
                {"severity": sev, "description": f"Finding {i}"}
                for i, sev in enumerate(severities)
            ]
        )

        persist_review_findings(
            findings_json,
            "test:1",
            1,
            archetype="skeptic",
            spec_name="test",
            task_group="1",
            knowledge_db_conn=conn,
            sink=mock_sink,
            run_id="run-test",
        )

        # Find the persisted audit event — must exist
        calls = mock_sink.emit_audit_event.call_args_list
        persisted_events = [
            c
            for c in calls
            if c.args[0].event_type == AuditEventType.REVIEW_FINDINGS_PERSISTED
        ]
        assert len(persisted_events) == 1, "Expected exactly one REVIEW_FINDINGS_PERSISTED event"

        event = persisted_events[0].args[0]
        row_count = conn.execute(
            "SELECT COUNT(*) FROM review_findings"
        ).fetchone()[0]
        assert event.payload["count"] == row_count

        conn.close()


# ---------------------------------------------------------------------------
# TS-84-P3: Block reason finding ID count capped at 3
# ---------------------------------------------------------------------------


class TestBlockReasonIdCapProperty:
    """TS-84-P3: Blocking reason contains at most 3 finding IDs."""

    @given(n=st.integers(min_value=1, max_value=10))
    @settings(max_examples=20)
    def test_finding_id_count_capped(self, n: int) -> None:
        """For any N critical findings, reason has min(N, 3) F- IDs."""
        from agent_fox.engine.result_handler import _format_block_reason
        from agent_fox.knowledge.review_store import ReviewFinding

        findings = [
            ReviewFinding(
                id=str(uuid.uuid4()),
                severity="critical",
                description=f"Critical issue number {i}",
                requirement_ref=None,
                spec_name="test",
                task_group="1",
                session_id="test:1:1",
            )
            for i in range(n)
        ]

        reason = _format_block_reason(
            archetype="skeptic",
            findings=findings,
            threshold=0,
            spec_name="test",
            task_group="1",
        )

        id_count = len(re.findall(r"F-", reason))
        assert id_count == min(n, 3)

        if n > 3:
            assert f"and {n - 3} more" in reason


# ---------------------------------------------------------------------------
# TS-84-P4: Severity filter monotonicity
# ---------------------------------------------------------------------------


class TestSeverityFilterMonotonicity:
    """TS-84-P4: Severity filter only returns findings at or above the level."""

    @given(filter_sev=st.sampled_from(SEVERITY_LEVELS))
    @settings(max_examples=10)
    def test_severity_filter_monotonic(self, filter_sev: str) -> None:
        """All returned findings have severity >= filter level."""
        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)

        from agent_fox.knowledge.review_store import ReviewFinding, insert_findings

        # Insert findings at all severity levels
        findings = [
            ReviewFinding(
                id=str(uuid.uuid4()),
                severity=sev,
                description=f"Finding at {sev}",
                requirement_ref=None,
                spec_name="test",
                task_group="1",
                session_id="test:1:1",
            )
            for sev in SEVERITY_LEVELS
        ]
        insert_findings(conn, findings)

        rows = query_findings(conn, severity=filter_sev)
        for row in rows:
            assert SEVERITY_ORDER[row.severity] <= SEVERITY_ORDER[filter_sev]

        conn.close()


# ---------------------------------------------------------------------------
# TS-84-P5: Findings table row count matches query count
# ---------------------------------------------------------------------------


class TestFindingsTableRowCount:
    """TS-84-P5: Formatted table and JSON output have correct item counts."""

    @given(findings=st.lists(finding_row_strategy(), min_size=1, max_size=20))
    @settings(max_examples=20)
    def test_json_output_length_matches(self, findings: list[FindingRow]) -> None:
        """JSON output has the same number of items as findings."""
        json_out = format_findings_table(findings, json_output=True)
        data = json.loads(json_out)
        assert len(data) == len(findings)


# ---------------------------------------------------------------------------
# TS-84-P6: Status summary omits specs without critical/major
# ---------------------------------------------------------------------------


class TestStatusSummaryOmission:
    """TS-84-P6: Status summary only includes specs with critical or major findings."""

    @given(
        specs_with_severities=st.lists(
            st.tuples(
                st.text(
                    min_size=1,
                    max_size=10,
                    alphabet="abcdefghijklmnopqrstuvwxyz",
                ),
                st.lists(
                    st.sampled_from(SEVERITY_LEVELS), min_size=1, max_size=5
                ),
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=20)
    def test_summary_only_includes_critical_major_specs(
        self, specs_with_severities: list[tuple[str, list[str]]]
    ) -> None:
        """Every spec in summary has critical > 0 or major > 0."""
        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)

        from agent_fox.knowledge.review_store import ReviewFinding, insert_findings

        for spec_name, severities in specs_with_severities:
            findings = [
                ReviewFinding(
                    id=str(uuid.uuid4()),
                    severity=sev,
                    description=f"Finding for {spec_name}",
                    requirement_ref=None,
                    spec_name=spec_name,
                    task_group="1",
                    session_id=f"{spec_name}:1:1",
                )
                for sev in severities
            ]
            insert_findings(conn, findings)

        summary = query_findings_summary(conn)
        for entry in summary:
            assert entry.critical > 0 or entry.major > 0

        conn.close()
