"""Unit tests for context rendering from DB records.

Test Spec: TS-27-9, TS-27-10, TS-27-11, TS-27-14, TS-27-17, TS-27-18
Requirements: 27-REQ-5.1, 27-REQ-5.2, 27-REQ-5.3, 27-REQ-5.E1, 27-REQ-5.E2,
              27-REQ-7.1, 27-REQ-7.2, 27-REQ-10.1, 27-REQ-10.2, 27-REQ-10.E1
"""

from __future__ import annotations

import uuid
from pathlib import Path

import duckdb
import pytest

from agent_fox.knowledge.review_store import (
    ReviewFinding,
    VerificationResult,
    insert_findings,
    insert_verdicts,
)
from agent_fox.session.prompt import (
    assemble_context,
    render_review_context,
    render_verification_context,
)


@pytest.fixture
def review_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with review tables."""
    from tests.unit.knowledge.conftest import create_schema

    conn = duckdb.connect(":memory:")
    create_schema(conn)
    yield conn  # type: ignore[misc]
    try:
        conn.close()
    except Exception:
        pass


def _make_finding(
    severity: str = "major",
    description: str = "Test finding",
    spec_name: str = "test_spec",
    session_id: str = "s1",
) -> ReviewFinding:
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group="1",
        session_id=session_id,
    )


def _make_verdict(
    requirement_id: str = "05-REQ-1.1",
    verdict: str = "PASS",
    evidence: str | None = "Tests pass",
    spec_name: str = "test_spec",
    session_id: str = "s1",
) -> VerificationResult:
    return VerificationResult(
        id=str(uuid.uuid4()),
        requirement_id=requirement_id,
        verdict=verdict,
        evidence=evidence,
        spec_name=spec_name,
        task_group="1",
        session_id=session_id,
    )


class TestRenderReviewContext:
    """TS-27-9: render review context from DB."""

    def test_render_review_context(
        self, review_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Active findings are rendered as Skeptic Review markdown."""
        findings = [
            _make_finding(severity="critical", description="Big problem"),
            _make_finding(severity="observation", description="Minor note"),
        ]
        insert_findings(review_conn, findings)

        result = render_review_context(review_conn, "test_spec")
        assert result is not None
        assert "## Skeptic Review" in result
        assert "### Critical Findings" in result
        assert "[severity: critical] Big problem" in result
        assert "[severity: observation] Minor note" in result
        assert "Summary:" in result


class TestRenderVerificationContext:
    """TS-27-10: render verification context from DB."""

    def test_render_verification_context(
        self, review_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Active verdicts are rendered as Verification Report markdown."""
        verdicts = [
            _make_verdict(requirement_id="05-REQ-1.1", verdict="PASS"),
            _make_verdict(
                requirement_id="05-REQ-2.1", verdict="FAIL", evidence="Not implemented"
            ),
        ]
        insert_verdicts(review_conn, verdicts)

        result = render_verification_context(review_conn, "test_spec")
        assert result is not None
        assert "## Verification Report" in result
        assert "05-REQ-1.1" in result
        assert "PASS" in result
        assert "FAIL" in result
        assert "Verdict: FAIL" in result


class TestRenderedFormatMatchesLegacy:
    """TS-27-11: rendered format matches legacy template format."""

    def test_rendered_format_matches_legacy(
        self, review_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Rendered markdown matches the expected structure."""
        findings = [
            _make_finding(severity="critical", description="Issue 1"),
            _make_finding(severity="major", description="Issue 2"),
        ]
        insert_findings(review_conn, findings)

        result = render_review_context(review_conn, "test_spec")
        assert result is not None

        # Check structure matches legacy format
        lines = result.split("\n")
        assert lines[0] == "## Skeptic Review"
        assert "### Critical Findings" in result
        assert "### Major Findings" in result
        assert "### Minor Findings" in result
        assert "### Observations" in result
        assert "Summary:" in result

    def test_verification_format_matches_legacy(
        self, review_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Verification context has table format."""
        verdicts = [_make_verdict()]
        insert_verdicts(review_conn, verdicts)

        result = render_verification_context(review_conn, "test_spec")
        assert result is not None

        # Check table structure
        assert "| Requirement | Status | Notes |" in result
        assert "|-------------|--------|-------|" in result
        assert "Verdict:" in result


class TestNoFindingsOmitsSection:
    """TS-27-E7: no findings means section is omitted."""

    def test_no_findings_omits_section(
        self, review_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """render_review_context returns None when no findings."""
        result = render_review_context(review_conn, "nonexistent_spec")
        assert result is None

    def test_no_verdicts_omits_section(
        self, review_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """render_verification_context returns None when no verdicts."""
        result = render_verification_context(review_conn, "nonexistent_spec")
        assert result is None


class TestDbUnavailableFallback:
    """TS-27-E6: DB unavailable falls back to file reading."""

    def test_db_unavailable_fallback(self, tmp_path: Path) -> None:
        """assemble_context works without DB connection (file fallback)."""
        spec_dir = tmp_path / "test_spec"
        spec_dir.mkdir()
        (spec_dir / "requirements.md").write_text("# Requirements\n")
        (spec_dir / "review.md").write_text(
            "# Skeptic Review\n- [severity: major] Test\n"
        )

        # No conn provided — falls back to file reading
        result = assemble_context(spec_dir, 1, conn=None)
        assert "Requirements" in result
        assert "Skeptic Review" in result

    def test_db_error_propagates(self, tmp_path: Path) -> None:
        """assemble_context propagates DB errors (38-REQ-3.E1).

        Updated from fallback behavior to error propagation per spec 38.
        """
        spec_dir = tmp_path / "test_spec"
        spec_dir.mkdir()
        (spec_dir / "requirements.md").write_text("# Requirements\n")
        (spec_dir / "review.md").write_text(
            "# Skeptic Review\n- [severity: minor] Fallback test\n"
        )

        # Use a closed connection to trigger an error
        conn = duckdb.connect(":memory:")
        conn.close()

        with pytest.raises(duckdb.ConnectionException):
            assemble_context(spec_dir, 1, conn=conn)


class TestGithubIssueBodyFromDb:
    """TS-27-14: GitHub issue body formatted from DB records."""

    def test_github_issue_body_from_db(self) -> None:
        """format_issue_body_from_findings creates markdown body."""
        from agent_fox.session.github_issues import format_issue_body_from_findings

        findings = [
            _make_finding(severity="critical", description="Blocker issue"),
            _make_finding(severity="major", description="Important issue"),
        ]
        body = format_issue_body_from_findings(findings)
        assert "## Blocking Findings" in body
        assert "### Critical" in body
        assert "Blocker issue" in body
        assert "### Major" in body
        assert "Important issue" in body

    def test_github_issue_close_empty(self) -> None:
        """Empty findings produce empty body."""
        from agent_fox.session.github_issues import format_issue_body_from_findings

        body = format_issue_body_from_findings([])
        assert body == ""


class TestGithubIssueDbUnavailable:
    """TS-27-E6 (partial): GitHub issue filing when DB unavailable."""

    def test_github_issue_db_unavailable(self) -> None:
        """format_issue_body_from_findings handles empty list gracefully."""
        from agent_fox.session.github_issues import format_issue_body_from_findings

        body = format_issue_body_from_findings([])
        assert body == ""


class TestLegacyFileMigration:
    """TS-27-17, TS-27-18: Legacy file migration via assemble_context."""

    def test_legacy_review_migration(self, tmp_path: Path) -> None:
        """Legacy review.md is migrated to DB on context assembly."""
        from tests.unit.knowledge.conftest import create_schema

        spec_dir = tmp_path / "test_spec"
        spec_dir.mkdir()
        (spec_dir / "requirements.md").write_text("# Requirements\n")
        (spec_dir / "review.md").write_text(
            "# Skeptic Review\n\n"
            "## Critical Findings\n"
            "- [severity: critical] Legacy finding\n"
        )

        conn = duckdb.connect(":memory:")
        create_schema(conn)

        result = assemble_context(spec_dir, 1, conn=conn)
        # Should contain the migrated finding rendered from DB
        assert "critical" in result.lower()
        assert "Legacy finding" in result
        conn.close()

    def test_legacy_verification_migration(self, tmp_path: Path) -> None:
        """Legacy verification.md is migrated to DB on context assembly."""
        from tests.unit.knowledge.conftest import create_schema

        spec_dir = tmp_path / "test_spec"
        spec_dir.mkdir()
        (spec_dir / "requirements.md").write_text("# Requirements\n")
        (spec_dir / "verification.md").write_text(
            "# Verification Report\n\n"
            "| Requirement | Status | Notes |\n"
            "|-------------|--------|-------|\n"
            "| 05-REQ-1.1 | PASS | OK |\n"
        )

        conn = duckdb.connect(":memory:")
        create_schema(conn)

        result = assemble_context(spec_dir, 1, conn=conn)
        assert "05-REQ-1.1" in result
        assert "PASS" in result
        conn.close()

    def test_legacy_parse_failure_skips(self, tmp_path: Path) -> None:
        """Bad legacy files are skipped without blocking."""
        from tests.unit.knowledge.conftest import create_schema

        spec_dir = tmp_path / "test_spec"
        spec_dir.mkdir()
        (spec_dir / "requirements.md").write_text("# Requirements\n")
        # Write something that won't match the pattern
        (spec_dir / "review.md").write_text("Random garbage content\n")

        conn = duckdb.connect(":memory:")
        create_schema(conn)

        # Should not raise
        result = assemble_context(spec_dir, 1, conn=conn)
        assert "Requirements" in result
        conn.close()
