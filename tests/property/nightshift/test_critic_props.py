"""Property tests for the finding consolidation critic.

Test Spec: TS-73-P1 through TS-73-P7
Properties: 1-7 from design.md
Requirements: 73-REQ-1.2, 73-REQ-4.1, 73-REQ-4.2, 73-REQ-4.E1, 73-REQ-5.1, 73-REQ-5.3,
              73-REQ-5.E1, 73-REQ-6.1, 73-REQ-6.2, 73-REQ-6.3, 73-REQ-7.E1
"""

from __future__ import annotations

import asyncio
import json

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_SEVERITIES = ("critical", "major", "minor", "info")

# Strategy for generating safe file path segments (no special chars)
_file_path_strategy = st.text(
    min_size=1,
    max_size=30,
    alphabet="abcdefghijklmnopqrstuvwxyz_./",
)


def _build_finding(
    category: str,
    title: str,
    description: str,
    severity: str,
    affected_files: list[str],
    suggested_fix: str,
    evidence: str,
    group_key: str,
) -> object:
    """Build a Finding from Hypothesis-generated arguments."""
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


_finding_strategy = st.builds(
    _build_finding,
    category=st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz_"),
    title=st.text(min_size=1, max_size=80, alphabet="abcdefghijklmnopqrstuvwxyz _"),
    description=st.text(min_size=1, max_size=150, alphabet="abcdefghijklmnopqrstuvwxyz _."),
    severity=st.sampled_from(_SEVERITIES),
    affected_files=st.lists(_file_path_strategy, min_size=0, max_size=5),
    suggested_fix=st.text(min_size=1, max_size=100, alphabet="abcdefghijklmnopqrstuvwxyz _."),
    evidence=st.text(min_size=1, max_size=100, alphabet="abcdefghijklmnopqrstuvwxyz _.:"),
    group_key=st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz-"),
)


# ---------------------------------------------------------------------------
# TS-73-P2: Mechanical grouping bijection
# Property 2 from design.md
# Requirements: 73-REQ-4.1, 73-REQ-4.2
# ---------------------------------------------------------------------------


class TestMechanicalGroupingBijection:
    """Below-threshold batches produce exactly one group per finding."""

    @given(findings=st.lists(_finding_strategy, min_size=0, max_size=2))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_mechanical_bijection(self, findings: list[object]) -> None:
        """_mechanical_grouping(findings) produces exactly len(findings) groups."""
        from agent_fox.nightshift.critic import _mechanical_grouping

        groups = _mechanical_grouping(findings)  # type: ignore[arg-type]
        assert len(groups) == len(findings)
        for group in groups:
            assert len(group.findings) == 1

    @given(findings=st.lists(_finding_strategy, min_size=1, max_size=2))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_mechanical_bijection_preserves_findings(self, findings: list[object]) -> None:
        """Each finding appears in exactly one group from _mechanical_grouping."""
        from agent_fox.nightshift.critic import _mechanical_grouping

        groups = _mechanical_grouping(findings)  # type: ignore[arg-type]
        all_grouped = [f for g in groups for f in g.findings]
        assert set(id(f) for f in all_grouped) == set(id(f) for f in findings)


# ---------------------------------------------------------------------------
# TS-73-P3: Affected files union
# Property 3 from design.md
# Requirements: 73-REQ-1.2
# ---------------------------------------------------------------------------


class TestAffectedFilesUnionProperty:
    """Mechanical grouping preserves each finding's affected files (sorted, deduped)."""

    @given(findings=st.lists(_finding_strategy, min_size=1, max_size=2))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_mechanical_affected_files_match_finding(self, findings: list[object]) -> None:
        """Each mechanical group's affected_files matches its single finding's files."""
        from agent_fox.nightshift.critic import _mechanical_grouping
        from agent_fox.nightshift.finding import Finding

        groups = _mechanical_grouping(findings)  # type: ignore[arg-type]
        for group, finding in zip(groups, findings):
            finding = finding  # type: ignore[assignment]
            assert isinstance(finding, Finding)
            expected = sorted(set(finding.affected_files))
            assert group.affected_files == expected


# ---------------------------------------------------------------------------
# TS-73-P4: Output format compatibility
# Property 4 from design.md
# Requirements: 73-REQ-5.1, 73-REQ-5.3
# ---------------------------------------------------------------------------


class TestOutputFormatCompatibility:
    """Every FindingGroup from mechanical grouping has non-empty title, body, findings.

    Requirements: 73-REQ-5.1, 73-REQ-5.3
    """

    @given(findings=st.lists(_finding_strategy, min_size=1, max_size=10))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_output_format_invariant(self, findings: list[object]) -> None:
        """All groups from _mechanical_grouping have non-empty title, body, findings."""
        from agent_fox.nightshift.critic import _mechanical_grouping

        groups = _mechanical_grouping(findings)  # type: ignore[arg-type]
        for group in groups:
            assert group.title != ""
            assert group.body != ""
            assert len(group.findings) > 0


# ---------------------------------------------------------------------------
# TS-73-P5: Graceful degradation
# Property 5 from design.md
# Requirements: 73-REQ-5.E1, 73-REQ-7.E1
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """AI backend failure produces the same result as mechanical grouping."""

    @given(findings=st.lists(_finding_strategy, min_size=3, max_size=10))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_ai_failure_equals_mechanical_output(self, findings: list[object]) -> None:
        """When AI raises, consolidate_findings returns len == _mechanical_grouping."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import (
            _mechanical_grouping,
            consolidate_findings,
        )

        expected = _mechanical_grouping(findings)  # type: ignore[arg-type]

        async def run() -> list[object]:
            with patch(
                "agent_fox.nightshift.critic._run_critic",
                new_callable=AsyncMock,
                side_effect=RuntimeError("backend down"),
            ):
                return await consolidate_findings(findings)  # type: ignore[arg-type]

        groups = asyncio.run(run())
        assert len(groups) == len(expected)


# ---------------------------------------------------------------------------
# TS-73-P6: Empty input invariant
# Property 6 from design.md
# Requirements: 73-REQ-4.E1
# ---------------------------------------------------------------------------


class TestEmptyInputInvariant:
    """Empty findings input always returns empty output."""

    def test_empty_input_always_empty_output(self) -> None:
        """consolidate_findings([]) returns [] in all cases."""
        from agent_fox.nightshift.critic import consolidate_findings

        groups = asyncio.run(consolidate_findings([]))
        assert groups == []

    def test_empty_mechanical_grouping(self) -> None:
        """_mechanical_grouping([]) returns []."""
        from agent_fox.nightshift.critic import _mechanical_grouping

        groups = _mechanical_grouping([])
        assert groups == []


# ---------------------------------------------------------------------------
# TS-73-P1: Finding conservation
# Property 1 from design.md
# Requirements: 73-REQ-1.1, 73-REQ-2.2, 73-REQ-5.3
# ---------------------------------------------------------------------------


class TestFindingConservation:
    """Every finding appears in a group or the dropped log — none silently lost."""

    @given(findings=st.lists(_finding_strategy, min_size=0, max_size=2))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_conservation_mechanical_path(self, findings: list[object]) -> None:
        """Below threshold: all findings appear in exactly one group."""
        from agent_fox.nightshift.critic import consolidate_findings

        groups = asyncio.run(consolidate_findings(findings))  # type: ignore[arg-type]
        found = {id(f) for g in groups for f in g.findings}
        # In the mechanical path, all findings are preserved
        assert len(found) == len(findings)

    @given(findings=st.lists(_finding_strategy, min_size=3, max_size=10))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_conservation_fallback_path(self, findings: list[object]) -> None:
        """When AI fails, all findings are preserved via mechanical fallback."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings

        async def run() -> list[object]:
            with patch(
                "agent_fox.nightshift.critic._run_critic",
                new_callable=AsyncMock,
                side_effect=RuntimeError("backend down"),
            ):
                return await consolidate_findings(findings)  # type: ignore[arg-type]

        groups = asyncio.run(run())
        found = {id(f) for g in groups for f in g.findings}
        # Fallback to mechanical: all findings conserved
        assert len(found) == len(findings)


# ---------------------------------------------------------------------------
# TS-73-P7: Decision completeness
# Property 7 from design.md
# Requirements: 73-REQ-6.1, 73-REQ-6.2, 73-REQ-6.3
# ---------------------------------------------------------------------------


def _make_complete_response(n: int, groups: list[list[int]], dropped: list[int]) -> str:
    """Build a critic JSON response that covers all n finding indices."""
    group_entries = [
        {
            "title": f"Group covering {indices}",
            "description": "Combined findings",
            "severity": "minor",
            "finding_indices": indices,
            "merge_reason": "Related",
        }
        for indices in groups
    ]
    dropped_entries = [{"finding_index": idx, "reason": "Dropped for testing"} for idx in dropped]
    return json.dumps({"groups": group_entries, "dropped": dropped_entries})


@st.composite
def _complete_partition_strategy(draw: st.DrawFn) -> tuple[int, str]:
    """Generate (n_findings, complete_response) where all indices are covered."""
    n = draw(st.integers(min_value=1, max_value=8))
    indices = list(range(n))

    # Decide how many to drop (0 to n//2)
    n_drop = draw(st.integers(min_value=0, max_value=n // 2))
    dropped = draw(st.lists(st.sampled_from(indices), min_size=n_drop, max_size=n_drop, unique=True)) if n > 0 else []

    remaining = [i for i in indices if i not in dropped]

    # Partition remaining into groups
    groups: list[list[int]] = []
    while remaining:
        size = draw(st.integers(min_value=1, max_value=max(1, len(remaining))))
        groups.append(remaining[:size])
        remaining = remaining[size:]

    return n, _make_complete_response(n, groups, dropped)


class TestDecisionCompleteness:
    """All findings are accounted for in critic decisions."""

    @given(data=_complete_partition_strategy())
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_decision_completeness(self, data: tuple[int, str]) -> None:
        """Complete response: _parse_critic_response accounts for all N indices."""
        from agent_fox.nightshift.critic import _parse_critic_response
        from agent_fox.nightshift.finding import Finding

        n, response = data

        # Build n findings
        findings = [
            Finding(
                category="test",
                title=f"Finding {i}",
                description="desc",
                severity="minor",
                affected_files=[],
                suggested_fix="fix",
                evidence="ev",
                group_key=f"gk-{i}",
            )
            for i in range(n)
        ]

        groups, decisions = _parse_critic_response(response, findings)

        # All findings accounted for: in a group's findings OR in dropped decisions
        grouped_ids = {id(f) for g in groups for f in g.findings}
        dropped_indices = {idx for d in decisions if d.action == "dropped" for idx in d.finding_indices}
        dropped_ids = {id(findings[i]) for i in dropped_indices if i < n}

        accounted_ids = grouped_ids | dropped_ids
        all_ids = {id(f) for f in findings}
        assert accounted_ids == all_ids
