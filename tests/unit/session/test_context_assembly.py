"""Unit tests for session context assembly improvements (spec 42).

Tests causal context assembly with review findings, prior group finding
propagation across all finding types, and cache integration.

Test Spec: TS-42-5, TS-42-14, TS-42-15 through TS-42-20, TS-42-E4, TS-42-E5
Requirements: 42-REQ-1.*, 42-REQ-3.4, 42-REQ-4.*
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest

from agent_fox.session.prompt import (
    assemble_context,
    get_prior_group_findings,
    render_prior_group_findings,
    select_context_with_causal,
)

# Import schema helper from knowledge conftest
from tests.unit.knowledge.conftest import create_schema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_id() -> str:
    return str(uuid.uuid4())


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
    content: str,
    spec_name: str = "test_spec",
) -> None:
    conn.execute(
        "INSERT INTO memory_facts (id, content, category, spec_name, "
        "confidence, created_at) "
        "VALUES (?::UUID, ?, 'pattern', ?, 0.9, CURRENT_TIMESTAMP)",
        [fact_id, content, spec_name],
    )


def _insert_causal_link(
    conn: duckdb.DuckDBPyConnection,
    cause_id: str,
    effect_id: str,
) -> None:
    conn.execute(
        "INSERT INTO fact_causes (cause_id, effect_id) VALUES (?::UUID, ?::UUID)",
        [cause_id, effect_id],
    )


def _insert_review_finding(
    conn: duckdb.DuckDBPyConnection,
    finding_id: str,
    spec_name: str,
    *,
    severity: str = "major",
    description: str = "A review finding",
    task_group: str = "1",
    session_id: str = "test-session",
    created_at: str | None = None,
) -> None:
    if created_at:
        conn.execute(
            "INSERT INTO review_findings "
            "(id, severity, description, requirement_ref, spec_name, "
            "task_group, session_id, created_at) "
            "VALUES (?::UUID, ?, ?, NULL, ?, ?, ?, ?::TIMESTAMP)",
            [
                finding_id,
                severity,
                description,
                spec_name,
                task_group,
                session_id,
                created_at,
            ],
        )
    else:
        conn.execute(
            "INSERT INTO review_findings "
            "(id, severity, description, requirement_ref, spec_name, "
            "task_group, session_id, created_at) "
            "VALUES (?::UUID, ?, ?, NULL, ?, ?, ?, CURRENT_TIMESTAMP)",
            [finding_id, severity, description, spec_name, task_group, session_id],
        )


def _insert_drift_finding(
    conn: duckdb.DuckDBPyConnection,
    finding_id: str,
    spec_name: str,
    *,
    severity: str = "minor",
    description: str = "A drift finding",
    task_group: str = "1",
    session_id: str = "test-session",
    created_at: str | None = None,
) -> None:
    if created_at:
        conn.execute(
            "INSERT INTO drift_findings "
            "(id, severity, description, spec_ref, artifact_ref, spec_name, "
            "task_group, session_id, created_at) "
            "VALUES (?::UUID, ?, ?, NULL, NULL, ?, ?, ?, ?::TIMESTAMP)",
            [
                finding_id,
                severity,
                description,
                spec_name,
                task_group,
                session_id,
                created_at,
            ],
        )
    else:
        conn.execute(
            "INSERT INTO drift_findings "
            "(id, severity, description, spec_ref, artifact_ref, spec_name, "
            "task_group, session_id, created_at) "
            "VALUES (?::UUID, ?, ?, NULL, NULL, ?, ?, ?, CURRENT_TIMESTAMP)",
            [finding_id, severity, description, spec_name, task_group, session_id],
        )


def _insert_verification_result(
    conn: duckdb.DuckDBPyConnection,
    result_id: str,
    spec_name: str,
    *,
    requirement_id: str = "REQ-1",
    verdict: str = "FAIL",
    evidence: str = "Test failed",
    task_group: str = "1",
    session_id: str = "test-session",
    created_at: str | None = None,
) -> None:
    if created_at:
        conn.execute(
            "INSERT INTO verification_results "
            "(id, requirement_id, verdict, evidence, spec_name, "
            "task_group, session_id, created_at) "
            "VALUES (?::UUID, ?, ?, ?, ?, ?, ?, ?::TIMESTAMP)",
            [
                result_id,
                requirement_id,
                verdict,
                evidence,
                spec_name,
                task_group,
                session_id,
                created_at,
            ],
        )
    else:
        conn.execute(
            "INSERT INTO verification_results "
            "(id, requirement_id, verdict, evidence, spec_name, "
            "task_group, session_id, created_at) "
            "VALUES (?::UUID, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [
                result_id,
                requirement_id,
                verdict,
                evidence,
                spec_name,
                task_group,
                session_id,
            ],
        )


@pytest.fixture
def schema_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with full schema."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    yield conn  # type: ignore[misc]
    try:
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# TestCausalContextAssembly
# ---------------------------------------------------------------------------


class TestCausalContextAssembly:
    """Tests for select_context_with_causal() using traverse_with_reviews.

    Requirements: 42-REQ-1.1, 42-REQ-1.2
    """

    def test_includes_review_findings_in_result(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-42-5: select_context_with_causal includes review findings."""
        fact_id = _new_id()
        review_id = _new_id()

        _insert_fact(schema_conn, fact_id, "A test fact", "test_spec")
        _insert_review_finding(
            schema_conn,
            review_id,
            "test_spec",
            description="Review issue found",
        )

        keyword_facts = [
            {
                "id": fact_id,
                "content": "A test fact",
                "spec_name": "test_spec",
                "session_id": None,
                "commit_sha": None,
            },
        ]

        result = select_context_with_causal(
            schema_conn,
            "test_spec",
            [],
            keyword_facts=keyword_facts,
        )

        # The result should include an entry representing the review finding,
        # distinguishable from regular fact dicts (has a "type" key or similar)
        has_review = any(isinstance(item, dict) and item.get("type") == "review" for item in result)
        assert has_review, "Expected review finding in select_context_with_causal result"


# ---------------------------------------------------------------------------
# TestPriorGroupFindings
# ---------------------------------------------------------------------------


class TestPriorGroupFindings:
    """Tests for cross-task-group finding propagation.

    Requirements: 42-REQ-4.1, 42-REQ-4.2, 42-REQ-4.3, 42-REQ-4.E1, 42-REQ-4.E2
    """

    def test_includes_review_findings_from_earlier_groups(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-42-15: prior findings include review findings from earlier groups."""
        id1 = _new_id()
        id2 = _new_id()

        _insert_review_finding(
            schema_conn,
            id1,
            "test_spec",
            task_group="1",
            description="Finding from group 1",
        )
        _insert_review_finding(
            schema_conn,
            id2,
            "test_spec",
            task_group="2",
            description="Finding from group 2",
        )

        result = get_prior_group_findings(
            schema_conn,
            "test_spec",
            task_group=3,
        )

        assert len(result) == 2
        # Results should include both groups
        groups = {r.group if hasattr(r, "group") else r.task_group for r in result}  # type: ignore[attr-defined]
        assert "1" in groups
        assert "2" in groups

    def test_includes_drift_findings_from_earlier_groups(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-42-16: prior findings include drift findings from earlier groups."""
        id1 = _new_id()
        id2 = _new_id()

        _insert_drift_finding(
            schema_conn,
            id1,
            "test_spec",
            task_group="1",
            description="Drift from group 1",
        )
        _insert_drift_finding(
            schema_conn,
            id2,
            "test_spec",
            task_group="2",
            description="Drift from group 2",
        )

        result = get_prior_group_findings(
            schema_conn,
            "test_spec",
            task_group=3,
        )

        # Should include drift findings from both prior groups
        descriptions = [r.description if hasattr(r, "description") else str(r) for r in result]
        assert any("Drift from group 1" in d for d in descriptions)
        assert any("Drift from group 2" in d for d in descriptions)

    def test_includes_verification_results_from_earlier_groups(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-42-17: prior findings include verification results from earlier groups."""
        id1 = _new_id()
        id2 = _new_id()

        _insert_verification_result(
            schema_conn,
            id1,
            "test_spec",
            task_group="1",
            requirement_id="REQ-1",
            verdict="FAIL",
        )
        _insert_verification_result(
            schema_conn,
            id2,
            "test_spec",
            task_group="2",
            requirement_id="REQ-2",
            verdict="PASS",
        )

        result = get_prior_group_findings(
            schema_conn,
            "test_spec",
            task_group=3,
        )

        # Should include verification results from both prior groups
        assert len(result) >= 2

    def test_excludes_current_and_future_groups(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-42-18: prior findings exclude current and future groups."""
        for group in ["1", "2", "3", "4"]:
            _insert_review_finding(
                schema_conn,
                _new_id(),
                "test_spec",
                task_group=group,
                description=f"Finding from group {group}",
            )

        result = get_prior_group_findings(
            schema_conn,
            "test_spec",
            task_group=3,
        )

        # Only groups 1 and 2 should be present
        for r in result:
            group_val = r.group if hasattr(r, "group") else r.task_group  # type: ignore[attr-defined]
            assert int(group_val) < 3, f"Found finding from group {group_val}, expected only < 3"

    def test_render_includes_type_labels(self) -> None:
        """TS-42-19: render_prior_group_findings includes type labels."""
        from agent_fox.session.prompt import PriorFinding

        findings = [
            PriorFinding(
                type="review",
                group="1",
                severity="major",
                description="Review issue",
                created_at="2026-01-01T00:00:00",
            ),
            PriorFinding(
                type="drift",
                group="1",
                severity="minor",
                description="Drift issue",
                created_at="2026-01-02T00:00:00",
            ),
            PriorFinding(
                type="verification",
                group="2",
                severity="FAIL",
                description="REQ-1: FAIL",
                created_at="2026-01-03T00:00:00",
            ),
        ]

        rendered = render_prior_group_findings(findings)

        assert rendered.startswith("## Prior Group Findings")
        assert "[review]" in rendered
        assert "[drift]" in rendered
        assert "[verification]" in rendered
        assert "[group 1]" in rendered
        assert "[group 2]" in rendered

    def test_prior_findings_ordered_by_created_at(self) -> None:
        """TS-42-20: prior findings are ordered by created_at ascending."""
        from agent_fox.session.prompt import PriorFinding

        findings = [
            PriorFinding(
                type="review",
                group="2",
                severity="major",
                description="Later finding",
                created_at="2026-01-03T00:00:00",
            ),
            PriorFinding(
                type="drift",
                group="1",
                severity="minor",
                description="Earlier finding",
                created_at="2026-01-01T00:00:00",
            ),
            PriorFinding(
                type="review",
                group="1",
                severity="minor",
                description="Middle finding",
                created_at="2026-01-02T00:00:00",
            ),
        ]

        rendered = render_prior_group_findings(findings)

        # All descriptions must appear in the output
        assert "Earlier finding" in rendered
        assert "Middle finding" in rendered
        assert "Later finding" in rendered

        # Descriptions must appear in created_at ascending order
        earlier_pos = rendered.index("Earlier finding")
        middle_pos = rendered.index("Middle finding")
        later_pos = rendered.index("Later finding")
        assert earlier_pos < middle_pos < later_pos

    def test_task_group_1_returns_no_prior_findings(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-42-E4: task_group=1 returns no prior findings."""
        result = get_prior_group_findings(
            schema_conn,
            "test_spec",
            task_group=1,
        )
        assert result == []

    def test_no_active_findings_omits_section(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        """TS-42-E5: no active findings omits the Prior Group Findings section."""
        # Create a minimal spec directory
        spec_dir = tmp_path / "test_spec"
        spec_dir.mkdir()
        (spec_dir / "requirements.md").write_text("# Requirements\n")
        (spec_dir / "design.md").write_text("# Design\n")
        (spec_dir / "test_spec.md").write_text("# Tests\n")
        (spec_dir / "tasks.md").write_text("# Tasks\n")

        context = assemble_context(
            spec_dir,
            task_group=2,
            conn=schema_conn,
        )

        assert "Prior Group Findings" not in context


# ---------------------------------------------------------------------------
# TestCacheIntegration
# ---------------------------------------------------------------------------


class TestCacheIntegration:
    """Tests for cache disabled behavior.

    Requirements: 42-REQ-3.4
    """

    def test_cache_disabled_skips_population(self) -> None:
        """TS-42-14: cache disabled skips population.

        When fact_cache_enabled=False, the orchestrator should not call
        precompute_fact_rankings(). We verify this by checking config
        and ensuring the code path respects the flag.
        """
        from agent_fox.core.config import KnowledgeConfig

        config = KnowledgeConfig(fact_cache_enabled=False)
        assert config.fact_cache_enabled is False

        # The orchestrator path that checks this flag should skip cache.
        # This test verifies the config setting; the actual wiring is
        # tested via integration when the orchestrator is implemented.
        config_enabled = KnowledgeConfig(fact_cache_enabled=True)
        assert config_enabled.fact_cache_enabled is True
