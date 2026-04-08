"""Property tests for Night Shift.

Test Spec: TS-61-P1 through TS-61-P8
Properties: 1-8 from design.md
Requirements: 61-REQ-1.3, 61-REQ-1.4, 61-REQ-1.E2, 61-REQ-2.1, 61-REQ-2.2,
              61-REQ-3.3, 61-REQ-3.E1, 61-REQ-5.1, 61-REQ-5.2, 61-REQ-6.2,
              61-REQ-7.1, 61-REQ-7.2, 61-REQ-8.1, 61-REQ-8.2, 61-REQ-8.3,
              61-REQ-9.1, 61-REQ-9.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_SEVERITIES = ("critical", "major", "minor", "info")

_finding_strategy = st.builds(
    lambda category, title, description, severity, affected_files, suggested_fix, evidence, group_key: (  # noqa: E501
        None
    ),
    category=st.text(min_size=1, max_size=50),
    title=st.text(min_size=1, max_size=100),
    description=st.text(min_size=1, max_size=200),
    severity=st.sampled_from(_SEVERITIES),
    affected_files=st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5),
    suggested_fix=st.text(min_size=1, max_size=200),
    evidence=st.text(min_size=1, max_size=200),
    group_key=st.text(min_size=1, max_size=50),
)


def _make_finding_from_args(
    category: str,
    title: str,
    description: str,
    severity: str,
    affected_files: list[str],
    suggested_fix: str,
    evidence: str,
    group_key: str,
) -> object:
    """Build a Finding from generated arguments."""
    from agent_fox.nightshift.finding import Finding

    return Finding(
        category=category,
        title=title,
        description=description,
        severity=severity,
        affected_files=affected_files,
        suggested_fix=suggested_fix,
        evidence=evidence,
        group_key=group_key,
    )


# ---------------------------------------------------------------------------
# TS-61-P1: Finding format universality
# Property 1: Every Finding has all required fields populated.
# Requirements: 61-REQ-3.3, 61-REQ-4.1, 61-REQ-4.2
# ---------------------------------------------------------------------------


class TestFindingFormatUniversality:
    """Every Finding has all required fields populated."""

    @given(
        category=st.text(min_size=1, max_size=50),
        title=st.text(min_size=1, max_size=100),
        description=st.text(min_size=1, max_size=200),
        severity=st.sampled_from(_SEVERITIES),
        affected_files=st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5),
        suggested_fix=st.text(min_size=1, max_size=200),
        evidence=st.text(min_size=1, max_size=200),
        group_key=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50)
    def test_finding_format_universality(
        self,
        category: str,
        title: str,
        description: str,
        severity: str,
        affected_files: list[str],
        suggested_fix: str,
        evidence: str,
        group_key: str,
    ) -> None:
        from agent_fox.nightshift.finding import Finding

        f = Finding(
            category=category,
            title=title,
            description=description,
            severity=severity,
            affected_files=affected_files,
            suggested_fix=suggested_fix,
            evidence=evidence,
            group_key=group_key,
        )
        assert f.category != ""
        assert f.title != ""
        assert f.description != ""
        assert f.severity in _SEVERITIES
        assert f.group_key != ""
        assert isinstance(f.affected_files, list)


# ---------------------------------------------------------------------------
# TS-61-P4: Fix pipeline completeness
# Property 4: Successful fix produces exactly one branch and one PR.
# Requirements: 61-REQ-6.2, 61-REQ-7.1, 61-REQ-7.2
# ---------------------------------------------------------------------------


class TestFixPipelineCompleteness:
    """Successful fix produces exactly one PR with correct references."""

    @given(
        issue_number=st.integers(min_value=1, max_value=10000),
        title=st.text(min_size=3, max_size=50, alphabet="abcdefghijklmnop "),
    )
    @settings(max_examples=20)
    def test_fix_pipeline_completeness(self, issue_number: int, title: str) -> None:
        from agent_fox.nightshift.fix_pipeline import build_pr_body
        from agent_fox.nightshift.spec_builder import sanitise_branch_name

        branch = sanitise_branch_name(title)
        assert branch.startswith("fix/")

        body = build_pr_body(issue_number=issue_number, summary="test fix")
        assert f"#{issue_number}" in body


# ---------------------------------------------------------------------------
# TS-61-P5: Cost monotonicity
# Property 5: Cost never decreases during a run.
# Requirements: 61-REQ-1.E2, 61-REQ-9.3
# ---------------------------------------------------------------------------


class TestCostMonotonicity:
    """Cost never decreases during a run."""

    @given(
        costs=st.lists(
            st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=50)
    def test_cost_monotonicity(self, costs: list[float]) -> None:
        from agent_fox.nightshift.state import NightShiftState

        state = NightShiftState()
        previous = 0.0
        for cost in costs:
            state.total_cost += cost
            assert state.total_cost >= previous
            previous = state.total_cost


# ---------------------------------------------------------------------------
# TS-61-P7: Category isolation
# Property 7: A failing category does not affect other categories.
# Requirements: 61-REQ-3.E1, 61-REQ-3.4
# ---------------------------------------------------------------------------


class TestCategoryIsolation:
    """A failing category does not affect other categories."""

    @given(
        failing_indices=st.lists(
            st.integers(min_value=0, max_value=2),
            min_size=0,
            max_size=3,
            unique=True,
        ),
    )
    @settings(max_examples=20)
    def test_category_isolation(self, failing_indices: list[int]) -> None:
        import asyncio
        from pathlib import Path
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.finding import Finding
        from agent_fox.nightshift.hunt import HuntCategoryRegistry, HuntScanner

        config = MagicMock()

        cat_names = ["cat_a", "cat_b", "cat_c"]
        mock_cats = []

        for i, name in enumerate(cat_names):
            mock = MagicMock()
            mock.name = name
            if i in failing_indices:
                mock.detect = AsyncMock(side_effect=RuntimeError("fail"))
            else:
                finding = Finding(
                    category=name,
                    title=f"Finding from {name}",
                    description="test",
                    severity="minor",
                    affected_files=[],
                    suggested_fix="fix",
                    evidence="ev",
                    group_key=f"gk-{name}",
                )
                mock.detect = AsyncMock(return_value=[finding])
            mock_cats.append(mock)

        registry = HuntCategoryRegistry()
        registry._categories = mock_cats  # type: ignore[assignment]

        scanner = HuntScanner(registry, config)

        findings = asyncio.run(scanner.run(Path("/tmp/test")))

        expected_count = len(cat_names) - len(failing_indices)
        assert len(findings) == expected_count


# ---------------------------------------------------------------------------
# TS-61-P8: Platform protocol substitutability
# Property 8: Any PlatformProtocol implementation works with the engine.
# Requirements: 61-REQ-8.1, 61-REQ-8.2, 61-REQ-8.3
# ---------------------------------------------------------------------------


class TestPlatformProtocolSubstitutability:
    """Any PlatformProtocol implementation works with the engine."""

    @given(data=st.data())
    @settings(max_examples=10)
    def test_platform_protocol_substitutability(self, data: st.DataObject) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.platform.protocol import PlatformProtocol

        # Create a mock that satisfies PlatformProtocol
        mock_platform = AsyncMock()
        mock_platform.create_issue = AsyncMock()
        mock_platform.list_issues_by_label = AsyncMock(return_value=[])
        mock_platform.add_issue_comment = AsyncMock()
        mock_platform.assign_label = AsyncMock()
        mock_platform.close_issue = AsyncMock()
        mock_platform.create_pull_request = AsyncMock()
        mock_platform.remove_label = AsyncMock()
        mock_platform.list_issue_comments = AsyncMock(return_value=[])
        mock_platform.get_issue = AsyncMock()
        mock_platform.close = AsyncMock()

        assert isinstance(mock_platform, PlatformProtocol)

        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None

        engine = NightShiftEngine(config=config, platform=mock_platform)

        # Should not raise TypeError
        asyncio.run(engine._run_issue_check())
