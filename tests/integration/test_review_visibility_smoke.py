"""Integration smoke tests for review archetype output visibility.

End-to-end tests that exercise real components (no mocking of core logic).

Test Spec: TS-84-SMOKE-1 through TS-84-SMOKE-5
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
from click.testing import CliRunner

from agent_fox.knowledge.review_store import (
    ReviewFinding,
    insert_findings,
)
from tests.unit.knowledge.conftest import SCHEMA_DDL


class TestFindingsPersistenceAuditE2E:
    """TS-84-SMOKE-2: Findings persistence emits audit event end-to-end.

    Real persist_review_findings inserts to DuckDB and emits audit event.
    """

    def test_findings_inserted_and_event_emitted(self) -> None:
        from agent_fox.engine.review_persistence import persist_review_findings
        from agent_fox.knowledge.audit import AuditEventType

        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)

        # Use a capturing mock sink (not mocking insert_findings or emit)
        mock_sink = MagicMock()

        transcript = json.dumps([{"severity": "critical", "description": "missing guard"}])

        persist_review_findings(
            transcript,
            "smoke:1",
            1,
            archetype="skeptic",
            spec_name="smoke",
            task_group="1",
            knowledge_db_conn=conn,
            sink=mock_sink,
            run_id="smoke-run",
        )

        # Verify rows in DB
        row_count = conn.execute("SELECT COUNT(*) FROM review_findings").fetchone()[0]  # type: ignore[index]
        assert row_count > 0

        # Verify audit event emitted
        calls = mock_sink.emit_audit_event.call_args_list
        persisted_events = [c for c in calls if c.args[0].event_type == AuditEventType.REVIEW_FINDINGS_PERSISTED]
        assert len(persisted_events) == 1

        conn.close()


class TestFindingsCLIE2E:
    """TS-84-SMOKE-3: Findings CLI command end-to-end.

    Real DB, real query, real formatting.
    """

    def test_cli_queries_real_db(self, tmp_path: Path) -> None:
        from agent_fox.cli.findings import findings_cmd

        # Set up a real DuckDB with test data
        db_path = tmp_path / "knowledge.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(SCHEMA_DDL)

        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="missing guard",
            requirement_ref=None,
            spec_name="smoke_spec",
            task_group="1",
            session_id="smoke_spec:1:1",
        )
        insert_findings(conn, [finding])
        conn.close()

        runner = CliRunner()
        with patch("agent_fox.cli.findings.DEFAULT_DB_PATH", db_path):
            result = runner.invoke(findings_cmd)

        assert result.exit_code == 0
        assert "missing guard" in result.output


class TestStatusFindingsSummaryE2E:
    """TS-84-SMOKE-4: Status findings summary end-to-end.

    Real DB with critical findings produces non-empty summary.
    """

    def test_summary_from_real_db(self) -> None:
        from agent_fox.reporting.findings import query_findings_summary

        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)

        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="critical issue",
            requirement_ref=None,
            spec_name="smoke_spec",
            task_group="1",
            session_id="smoke_spec:1:1",
        )
        insert_findings(conn, [finding])

        summary = query_findings_summary(conn)
        assert len(summary) > 0

        conn.close()


class TestEnrichedBlockingReasonE2E:
    """TS-84-SMOKE-5: Enriched blocking reason end-to-end.

    Real DB with critical findings produces enriched reason with F- IDs.
    """

    def test_enriched_reason_from_real_db(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        from agent_fox.engine.blocking import evaluate_review_blocking
        from agent_fox.engine.state import SessionRecord

        findings = [
            ReviewFinding(
                id=str(uuid.uuid4()),
                severity="critical",
                description="critical issue one",
                requirement_ref=None,
                spec_name="smoke_spec",
                task_group="1",
                session_id="smoke_spec:1:1",
            ),
            ReviewFinding(
                id=str(uuid.uuid4()),
                severity="critical",
                description="critical issue two",
                requirement_ref=None,
                spec_name="smoke_spec",
                task_group="1",
                session_id="smoke_spec:1:1",
            ),
        ]
        insert_findings(knowledge_conn, findings)

        record = SessionRecord(
            node_id="smoke_spec:1",
            archetype="skeptic",
            attempt=1,
            status="completed",
            input_tokens=100,
            output_tokens=50,
            cost=0.01,
            duration_ms=1000,
            error_message=None,
            timestamp="2026-04-07T00:00:00Z",
        )

        config = MagicMock()
        config.reviewer_config.pre_review_block_threshold = 0
        config.reviewer_config.drift_review_block_threshold = 0

        decision = evaluate_review_blocking(record, config, knowledge_conn)

        assert decision.should_block
        assert "F-" in decision.reason
        assert "critical" in decision.reason
