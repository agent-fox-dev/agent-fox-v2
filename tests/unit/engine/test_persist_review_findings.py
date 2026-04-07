"""Unit tests for NodeSessionRunner._persist_review_findings.

Validates that structured findings from skeptic, verifier, and oracle
sessions are parsed and persisted to DuckDB.

Requirements: 27-REQ-3.1, 27-REQ-4.1, 27-REQ-4.2

Updated for spec 38: Tests now use the shared knowledge_db fixture
(38-REQ-5.3) instead of creating inline duckdb.connect() connections.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, PropertyMock

from agent_fox.core.config import AgentFoxConfig
from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.knowledge.db import KnowledgeDB


class TestPersistSkepticFindings:
    """Skeptic findings are parsed from JSON and inserted into review_findings."""

    def test_findings_persisted(self, knowledge_db: KnowledgeDB) -> None:
        runner = NodeSessionRunner(
            "my_spec:0",
            AgentFoxConfig(),
            archetype="skeptic",
            knowledge_db=knowledge_db,
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

        rows = knowledge_db._conn.execute(  # type: ignore[union-attr]
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

    def test_no_json_logs_warning_no_crash(self, knowledge_db: KnowledgeDB) -> None:
        runner = NodeSessionRunner(
            "my_spec:0",
            AgentFoxConfig(),
            archetype="skeptic",
            knowledge_db=knowledge_db,
        )
        runner._persist_review_findings("No JSON here at all.", "my_spec:0", 1)

        rows = knowledge_db._conn.execute(  # type: ignore[union-attr]
            "SELECT COUNT(*) FROM review_findings"
        ).fetchone()
        assert rows is not None
        assert rows[0] == 0


class TestPersistVerifierVerdicts:
    """Verifier verdicts are parsed from JSON and inserted into verification_results."""

    def test_verdicts_persisted(self, knowledge_db: KnowledgeDB) -> None:
        runner = NodeSessionRunner(
            "my_spec:7",
            AgentFoxConfig(),
            archetype="verifier",
            knowledge_db=knowledge_db,
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

        rows = knowledge_db._conn.execute(  # type: ignore[union-attr]
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

    def test_drift_findings_persisted(self, knowledge_db: KnowledgeDB) -> None:
        runner = NodeSessionRunner("my_spec:0", AgentFoxConfig(), archetype="oracle", knowledge_db=knowledge_db)
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

        rows = knowledge_db._conn.execute(  # type: ignore[union-attr]
            "SELECT severity, description, spec_ref, artifact_ref, spec_name FROM drift_findings"
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

    def test_coder_does_nothing(self, knowledge_db: KnowledgeDB) -> None:
        runner = NodeSessionRunner("my_spec:1", AgentFoxConfig(), archetype="coder", knowledge_db=knowledge_db)
        transcript = json.dumps({"findings": [{"severity": "critical", "description": "x"}]})
        runner._persist_review_findings(transcript, "my_spec:1", 1)

        rows = knowledge_db._conn.execute(  # type: ignore[union-attr]
            "SELECT COUNT(*) FROM review_findings"
        ).fetchone()
        assert rows is not None
        assert rows[0] == 0


class TestParseFailureSwallowed:
    """DB or parse errors are logged but don't crash the session."""

    def test_db_error_swallowed(self) -> None:
        mock_kb = MagicMock(spec=KnowledgeDB)
        type(mock_kb).connection = PropertyMock(side_effect=RuntimeError("DB gone"))
        runner = NodeSessionRunner("my_spec:0", AgentFoxConfig(), archetype="skeptic", knowledge_db=mock_kb)
        # Should not raise
        runner._persist_review_findings('{"findings":[{"severity":"major","description":"x"}]}', "my_spec:0", 1)
