"""Unit tests for Finding, FindingGroup, consolidation, and issue body.

Test Spec: TS-61-9, TS-61-13, TS-61-15
Requirements: 61-REQ-3.3, 61-REQ-5.1, 61-REQ-5.3
"""

from __future__ import annotations


def _make_finding(**overrides: object) -> object:
    """Create a Finding with sensible defaults, overridden as needed."""
    from agent_fox.nightshift.finding import Finding

    defaults = {
        "category": "linter_debt",
        "title": "Unused imports in engine/",
        "description": "5 files contain unused imports.",
        "severity": "minor",
        "affected_files": ["agent_fox/engine/engine.py"],
        "suggested_fix": "Remove unused imports using ruff --fix",
        "evidence": "ruff output:\n...",
        "group_key": "unused-imports-engine",
    }
    defaults.update(overrides)
    return Finding(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TS-61-9: Hunt category interface contract
# Requirement: 61-REQ-3.3
# ---------------------------------------------------------------------------


class TestFindingContract:
    """Verify that Finding has all required fields."""

    def test_finding_has_required_fields(self) -> None:
        """Every Finding must have all required fields populated."""
        from agent_fox.nightshift.finding import Finding

        f = _make_finding()
        assert isinstance(f, Finding)
        assert f.category != ""
        assert f.title != ""
        assert f.description != ""
        assert f.severity in ("critical", "major", "minor", "info")
        assert f.group_key != ""
        assert isinstance(f.affected_files, list)

    def test_finding_is_frozen(self) -> None:
        """Finding should be immutable (frozen dataclass)."""
        import pytest

        f = _make_finding()
        with pytest.raises((AttributeError, TypeError)):
            f.title = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TS-61-13: Finding grouping by root cause
# Requirement: 61-REQ-5.1
# ---------------------------------------------------------------------------


class TestFindingConsolidation:
    """Verify that findings are grouped by root cause (group_key)."""

    def test_group_by_root_cause(self) -> None:
        """4 findings with 2 group_keys produce 2 groups."""
        from agent_fox.nightshift.finding import consolidate_findings

        findings = [
            _make_finding(group_key="unused-imports", title="A"),
            _make_finding(group_key="unused-imports", title="B"),
            _make_finding(group_key="missing-docstring", title="C"),
            _make_finding(group_key="missing-docstring", title="D"),
        ]
        groups = consolidate_findings(findings)
        assert len(groups) == 2
        group_sizes = sorted(len(g.findings) for g in groups)
        assert group_sizes == [2, 2]

    def test_single_finding_per_group(self) -> None:
        """3 findings with distinct group_keys produce 3 groups."""
        from agent_fox.nightshift.finding import consolidate_findings

        findings = [
            _make_finding(group_key="a"),
            _make_finding(group_key="b"),
            _make_finding(group_key="c"),
        ]
        groups = consolidate_findings(findings)
        assert len(groups) == 3

    def test_all_findings_preserved(self) -> None:
        """Every finding appears in exactly one group."""
        from agent_fox.nightshift.finding import consolidate_findings

        findings = [
            _make_finding(group_key="x", title="1"),
            _make_finding(group_key="x", title="2"),
            _make_finding(group_key="y", title="3"),
        ]
        groups = consolidate_findings(findings)
        all_grouped = [f for g in groups for f in g.findings]
        assert len(all_grouped) == len(findings)
        assert set(id(f) for f in all_grouped) == set(id(f) for f in findings)


# ---------------------------------------------------------------------------
# TS-61-15: Issue body contains required fields
# Requirement: 61-REQ-5.3
# ---------------------------------------------------------------------------


class TestIssueBody:
    """Verify that issue body includes category, severity, files, and fix."""

    def test_issue_body_contains_category(self) -> None:
        """Issue body contains the category name."""
        from agent_fox.nightshift.finding import FindingGroup, build_issue_body

        group = FindingGroup(
            findings=[_make_finding(category="linter_debt", severity="minor")],
            title="Linter debt in engine",
            body="",
            category="linter_debt",
        )
        body = build_issue_body(group)
        assert "linter_debt" in body

    def test_issue_body_contains_severity(self) -> None:
        """Issue body contains the severity level."""
        from agent_fox.nightshift.finding import FindingGroup, build_issue_body

        group = FindingGroup(
            findings=[_make_finding(severity="minor")],
            title="Test",
            body="",
            category="linter_debt",
        )
        body = build_issue_body(group)
        assert "minor" in body

    def test_issue_body_contains_files(self) -> None:
        """Issue body contains affected file paths."""
        from agent_fox.nightshift.finding import FindingGroup, build_issue_body

        group = FindingGroup(
            findings=[
                _make_finding(affected_files=["foo.py", "bar.py"]),
            ],
            title="Test",
            body="",
            category="linter_debt",
        )
        body = build_issue_body(group)
        assert "foo.py" in body

    def test_issue_body_contains_suggested_fix(self) -> None:
        """Issue body contains suggested remediation."""
        from agent_fox.nightshift.finding import FindingGroup, build_issue_body

        group = FindingGroup(
            findings=[_make_finding(suggested_fix="Run ruff --fix")],
            title="Test",
            body="",
            category="linter_debt",
        )
        body = build_issue_body(group)
        lower = body.lower()
        assert "suggested" in lower or "remediation" in lower or "fix" in lower
