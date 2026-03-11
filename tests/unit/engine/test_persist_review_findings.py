"""Unit tests for NodeSessionRunner._persist_review_findings.

Validates that structured findings from skeptic, verifier, and oracle
sessions are parsed and persisted to DuckDB.

Requirements: 27-REQ-3.1, 27-REQ-4.1, 27-REQ-4.2
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, PropertyMock

import duckdb

from agent_fox.core.config import AgentFoxConfig
from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.knowledge.db import KnowledgeDB


def _make_db() -> MagicMock:
    """Create a mock KnowledgeDB backed by an in-memory DuckDB."""
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE review_findings (
            id              UUID PRIMARY KEY,
            severity        TEXT NOT NULL,
            description     TEXT NOT NULL,
            requirement_ref TEXT,
            spec_name       TEXT NOT NULL,
            task_group      TEXT NOT NULL,
            session_id      TEXT NOT NULL,
            superseded_by   TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE verification_results (
            id              UUID PRIMARY KEY,
            requirement_id  TEXT NOT NULL,
            verdict         TEXT NOT NULL,
            evidence        TEXT,
            spec_name       TEXT NOT NULL,
            task_group      TEXT NOT NULL,
            session_id      TEXT NOT NULL,
            superseded_by   TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE drift_findings (
            id              UUID PRIMARY KEY,
            severity        VARCHAR NOT NULL,
            description     VARCHAR NOT NULL,
            spec_ref        VARCHAR,
            artifact_ref    VARCHAR,
            spec_name       VARCHAR NOT NULL,
            task_group      VARCHAR NOT NULL,
            session_id      VARCHAR NOT NULL,
            superseded_by   UUID,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE fact_causes (
            cause_id  UUID,
            effect_id UUID,
            PRIMARY KEY (cause_id, effect_id)
        );
    """)
    mock_kb = MagicMock(spec=KnowledgeDB)
    type(mock_kb).connection = PropertyMock(return_value=conn)
    # Stash conn so tests can query it directly
    mock_kb._test_conn = conn
    return mock_kb


class TestPersistSkepticFindings:
    """Skeptic findings are parsed from JSON and inserted into review_findings."""

    def test_findings_persisted(self) -> None:
        mock_kb = _make_db()
        runner = NodeSessionRunner(
            "my_spec:0", AgentFoxConfig(), archetype="skeptic", knowledge_db=mock_kb
        )
        transcript = json.dumps(
            {
                "findings": [
                    {
                        "severity": "critical",
                        "description": "Missing error handling for null input",
                        "requirement_ref": "01-REQ-1.1",
                    },
                    {
                        "severity": "minor",
                        "description": "Docstring inconsistency",
                    },
                ]
            }
        )
        runner._persist_review_findings(transcript, "my_spec:0", 1)

        rows = mock_kb._test_conn.execute(
            "SELECT severity, description, requirement_ref, spec_name, task_group "
            "FROM review_findings ORDER BY severity"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0] == (
            "critical",
            "Missing error handling for null input",
            "01-REQ-1.1",
            "my_spec",
            "0",
        )
        assert rows[1] == ("minor", "Docstring inconsistency", None, "my_spec", "0")

    def test_no_json_logs_warning_no_crash(self) -> None:
        mock_kb = _make_db()
        runner = NodeSessionRunner(
            "my_spec:0", AgentFoxConfig(), archetype="skeptic", knowledge_db=mock_kb
        )
        runner._persist_review_findings("No JSON here at all.", "my_spec:0", 1)

        rows = mock_kb._test_conn.execute(
            "SELECT COUNT(*) FROM review_findings"
        ).fetchone()
        assert rows[0] == 0


class TestPersistVerifierVerdicts:
    """Verifier verdicts are parsed from JSON and inserted into verification_results."""

    def test_verdicts_persisted(self) -> None:
        mock_kb = _make_db()
        runner = NodeSessionRunner(
            "my_spec:7", AgentFoxConfig(), archetype="verifier", knowledge_db=mock_kb
        )
        transcript = json.dumps(
            {
                "verdicts": [
                    {
                        "requirement_id": "01-REQ-1.1",
                        "verdict": "PASS",
                        "evidence": "Test passes",
                    },
                    {
                        "requirement_id": "01-REQ-2.1",
                        "verdict": "FAIL",
                        "evidence": "Returns None instead of raising",
                    },
                ]
            }
        )
        runner._persist_review_findings(transcript, "my_spec:7", 1)

        rows = mock_kb._test_conn.execute(
            "SELECT requirement_id, verdict, evidence, spec_name, task_group "
            "FROM verification_results ORDER BY requirement_id"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0] == ("01-REQ-1.1", "PASS", "Test passes", "my_spec", "7")
        assert rows[1] == (
            "01-REQ-2.1",
            "FAIL",
            "Returns None instead of raising",
            "my_spec",
            "7",
        )


class TestPersistOracleDrift:
    """Oracle drift findings are parsed and inserted into drift_findings."""

    def test_drift_findings_persisted(self) -> None:
        mock_kb = _make_db()
        runner = NodeSessionRunner(
            "my_spec:0", AgentFoxConfig(), archetype="oracle", knowledge_db=mock_kb
        )
        transcript = json.dumps(
            {
                "drift_findings": [
                    {
                        "severity": "major",
                        "description": "Implementation diverges from spec",
                        "spec_ref": "design.md#api",
                        "artifact_ref": "src/api.py:42",
                    },
                ]
            }
        )
        runner._persist_review_findings(transcript, "my_spec:0", 1)

        rows = mock_kb._test_conn.execute(
            "SELECT severity, description, spec_ref, artifact_ref, spec_name "
            "FROM drift_findings"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0] == (
            "major",
            "Implementation diverges from spec",
            "design.md#api",
            "src/api.py:42",
            "my_spec",
        )


class TestCoderSkipped:
    """Non-review archetypes are silently skipped."""

    def test_coder_does_nothing(self) -> None:
        mock_kb = _make_db()
        runner = NodeSessionRunner(
            "my_spec:1", AgentFoxConfig(), archetype="coder", knowledge_db=mock_kb
        )
        transcript = json.dumps(
            {"findings": [{"severity": "critical", "description": "x"}]}
        )
        runner._persist_review_findings(transcript, "my_spec:1", 1)

        rows = mock_kb._test_conn.execute(
            "SELECT COUNT(*) FROM review_findings"
        ).fetchone()
        assert rows[0] == 0


class TestParseFailureSwallowed:
    """DB or parse errors are logged but don't crash the session."""

    def test_db_error_swallowed(self) -> None:
        mock_kb = MagicMock(spec=KnowledgeDB)
        type(mock_kb).connection = PropertyMock(side_effect=RuntimeError("DB gone"))
        runner = NodeSessionRunner(
            "my_spec:0", AgentFoxConfig(), archetype="skeptic", knowledge_db=mock_kb
        )
        # Should not raise
        runner._persist_review_findings(
            '{"findings":[{"severity":"major","description":"x"}]}', "my_spec:0", 1
        )
