"""Unit tests for enriched blocking reason formatting.

Validates that when a skeptic blocks a task, the blocking reason includes
finding IDs and truncated descriptions, and caps at 3 finding IDs.

Test Spec: TS-84-6, TS-84-7
Requirements: 84-REQ-3.1, 84-REQ-3.E1
"""

from __future__ import annotations

import re
import uuid
from unittest.mock import MagicMock

import duckdb

from agent_fox.engine.blocking import evaluate_review_blocking
from agent_fox.engine.state import SessionRecord
from agent_fox.knowledge.review_store import ReviewFinding, insert_findings


def _make_finding(
    *,
    severity: str = "critical",
    description: str = "Missing error handling for null input",
    spec_name: str = "my_spec",
    task_group: str = "1",
    session_id: str = "my_spec:1:1",
) -> ReviewFinding:
    """Create a ReviewFinding with a random UUID."""
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group=task_group,
        session_id=session_id,
    )


def _make_session_record(
    node_id: str = "my_spec:1",
    archetype: str = "skeptic",
    attempt: int = 1,
) -> SessionRecord:
    """Create a minimal SessionRecord for blocking evaluation."""
    return SessionRecord(
        node_id=node_id,
        archetype=archetype,
        attempt=attempt,
        status="completed",
        input_tokens=0,
        output_tokens=0,
        cost=0.0,
        duration_ms=0,
        error_message=None,
        timestamp="2026-01-01T00:00:00",
    )


def _make_archetypes_config(block_threshold: int = 0):
    """Create a mock ArchetypesConfig with given block threshold."""
    config = MagicMock()
    config.reviewer_config.pre_review_block_threshold = block_threshold
    config.reviewer_config.drift_review_block_threshold = block_threshold
    return config


class TestEnrichedBlockingReason:
    """TS-84-6: Enriched blocking reason includes finding IDs."""

    def test_blocking_reason_contains_finding_ids(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify blocked reason contains finding IDs and truncated descriptions."""
        findings = [
            _make_finding(description="Missing error handling for null input"),
            _make_finding(description="No validation on user-supplied data"),
        ]
        insert_findings(knowledge_conn, findings)

        record = _make_session_record()
        config = _make_archetypes_config(block_threshold=0)

        decision = evaluate_review_blocking(record, config, knowledge_conn)

        assert decision.should_block is True
        assert "2 critical" in decision.reason
        # Should contain F- prefixed finding IDs
        assert "F-" in decision.reason
        assert len(decision.reason) < 500  # reasonably sized

    def test_blocking_reason_contains_descriptions(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify blocked reason contains truncated descriptions."""
        findings = [
            _make_finding(description="Missing error handling for null input"),
        ]
        insert_findings(knowledge_conn, findings)

        record = _make_session_record()
        config = _make_archetypes_config(block_threshold=0)

        decision = evaluate_review_blocking(record, config, knowledge_conn)

        assert decision.should_block is True
        # Description should appear (possibly truncated) in the reason
        assert "Missing error handling" in decision.reason


class TestBlockingReasonFindingIdCap:
    """TS-84-7: Blocking reason caps at 3 finding IDs."""

    def test_caps_at_3_finding_ids(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify that with 5 critical findings, only 3 IDs are shown."""
        findings = [_make_finding(description=f"Critical issue {i}") for i in range(5)]
        insert_findings(knowledge_conn, findings)

        record = _make_session_record()
        config = _make_archetypes_config(block_threshold=0)

        decision = evaluate_review_blocking(record, config, knowledge_conn)

        assert decision.should_block is True
        # Count F- prefixed IDs in the reason string
        f_id_count = len(re.findall(r"F-", decision.reason))
        assert f_id_count == 3
        assert "and 2 more" in decision.reason
