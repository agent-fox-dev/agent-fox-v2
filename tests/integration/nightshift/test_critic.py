"""Integration tests for the finding consolidation critic.

Test Spec: TS-73-1, TS-73-3, TS-73-4, TS-73-6, TS-73-9,
           TS-73-E1, TS-73-E2, TS-73-E3, TS-73-E4, TS-73-E5, TS-73-E7, TS-73-E9
Requirements: 73-REQ-1.1, 73-REQ-1.3, 73-REQ-2.1, 73-REQ-2.2, 73-REQ-3.1, 73-REQ-3.E1,
              73-REQ-5.1, 73-REQ-5.3, 73-REQ-5.E1, 73-REQ-7.E1, 73-REQ-2.E1, 73-REQ-2.E2
"""

from __future__ import annotations

import json
import logging

import pytest


def _make_finding(**overrides: object) -> object:
    """Create a Finding with sensible defaults, overridden as needed."""
    from agent_fox.nightshift.finding import Finding

    defaults: dict[str, object] = {
        "category": "linter_debt",
        "title": "Test finding",
        "description": "Test description",
        "severity": "minor",
        "affected_files": ["test.py"],
        "suggested_fix": "Fix it",
        "evidence": "ruff: F401 test.py:1",
        "group_key": "test-group",
    }
    defaults.update(overrides)
    return Finding(**defaults)  # type: ignore[arg-type]


def _make_critic_response(
    groups: list[dict[str, object]],
    dropped: list[dict[str, object]] | None = None,
) -> str:
    """Build a valid critic JSON response string."""
    return json.dumps({"groups": groups, "dropped": dropped or []})


# ---------------------------------------------------------------------------
# TS-73-1: Cross-category merge
# Requirements: 73-REQ-1.1
# ---------------------------------------------------------------------------


class TestCrossCategoryMerge:
    """Findings from different categories sharing a root cause are merged."""

    @pytest.mark.asyncio
    async def test_cross_category_merge(self) -> None:
        """Findings A (dead_code) and B (linter_debt) are merged; C is standalone."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(
            category="dead_code",
            title="Unused auth helper",
            affected_files=["auth.py"],
            evidence="ruff: F811 auth.py:42",
            group_key="auth-unused",
        )
        finding_b = _make_finding(
            category="linter_debt",
            title="Unused import in auth module",
            affected_files=["auth.py"],
            evidence="ruff: F401 auth.py:1",
            group_key="auth-lint",
        )
        finding_c = _make_finding(
            category="test_coverage",
            title="Low coverage in payments",
            affected_files=["payments.py"],
            evidence="coverage: 12% payments.py",
            group_key="payments-coverage",
        )

        mock_response = _make_critic_response(
            groups=[
                {
                    "title": "Auth module issues: unused helper and import",
                    "description": "Two auth-related findings share the same cause.",
                    "severity": "minor",
                    "finding_indices": [0, 1],
                    "merge_reason": "Both findings flag the same unused auth module",
                },
                {
                    "title": "Low coverage in payments",
                    "description": "Payments module has insufficient test coverage.",
                    "severity": "minor",
                    "finding_indices": [2],
                    "merge_reason": "Standalone finding",
                },
            ]
        )

        with patch(
            "agent_fox.nightshift.critic._run_critic",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            groups = await consolidate_findings([finding_a, finding_b, finding_c])  # type: ignore[list-item]

        assert len(groups) == 2
        findings_in_groups = [set(id(f) for f in g.findings) for g in groups]
        merged_set = {id(finding_a), id(finding_b)}
        assert merged_set in findings_in_groups


# ---------------------------------------------------------------------------
# TS-73-3: Synthesised title and body
# Requirements: 73-REQ-1.3
# ---------------------------------------------------------------------------


class TestSynthesisedTitleBody:
    """Merged FindingGroup uses the critic's synthesised title and body."""

    @pytest.mark.asyncio
    async def test_synthesised_title_used(self) -> None:
        """The FindingGroup title matches the critic's synthesised title."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(title="Finding Alpha", group_key="alpha")
        finding_b = _make_finding(title="Finding Beta", group_key="beta")
        finding_c = _make_finding(
            title="Unrelated finding",
            group_key="unrelated",
            evidence="coverage: 12% other.py",
        )

        synthesised_title = "Synthesised title from critic"
        synthesised_description = "This is the synthesised description combining both findings"

        mock_response = _make_critic_response(
            groups=[
                {
                    "title": synthesised_title,
                    "description": synthesised_description,
                    "severity": "minor",
                    "finding_indices": [0, 1],
                    "merge_reason": "Related root cause",
                },
                {
                    "title": "Unrelated finding",
                    "description": "Standalone unrelated issue",
                    "severity": "minor",
                    "finding_indices": [2],
                    "merge_reason": "Standalone",
                },
            ]
        )

        with patch(
            "agent_fox.nightshift.critic._run_critic",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            groups = await consolidate_findings([finding_a, finding_b, finding_c])  # type: ignore[list-item]

        merged_group = next(g for g in groups if len(g.findings) > 1)
        assert merged_group.title == synthesised_title
        assert "synthesised description" in merged_group.body.lower() or synthesised_description in merged_group.body


# ---------------------------------------------------------------------------
# TS-73-4: Evidence validation drops finding
# Requirements: 73-REQ-2.1, 73-REQ-2.2
# ---------------------------------------------------------------------------


class TestEvidenceValidationDrops:
    """Findings with empty or speculative evidence are dropped."""

    @pytest.mark.asyncio
    async def test_empty_evidence_finding_dropped(self) -> None:
        """Finding B with empty evidence is dropped; A and C are retained."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(
            title="Finding A",
            evidence="ruff: F401 auth.py:1",
            group_key="a",
        )
        finding_b = _make_finding(
            title="Finding B",
            evidence="",  # empty — should be dropped
            group_key="b",
        )
        finding_c = _make_finding(
            title="Finding C",
            evidence="coverage: 12% payments.py",
            group_key="c",
        )

        mock_response = _make_critic_response(
            groups=[
                {
                    "title": "Finding A",
                    "description": "Concrete finding A",
                    "severity": "minor",
                    "finding_indices": [0],
                    "merge_reason": "Standalone",
                },
                {
                    "title": "Finding C",
                    "description": "Concrete finding C",
                    "severity": "minor",
                    "finding_indices": [2],
                    "merge_reason": "Standalone",
                },
            ],
            dropped=[
                {
                    "finding_index": 1,
                    "reason": "Evidence field is empty; finding is speculative",
                }
            ],
        )

        with patch(
            "agent_fox.nightshift.critic._run_critic",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            groups = await consolidate_findings([finding_a, finding_b, finding_c])  # type: ignore[list-item]

        all_findings = [f for g in groups for f in g.findings]
        assert finding_b not in all_findings
        assert len(all_findings) == 2


# ---------------------------------------------------------------------------
# TS-73-6: Severity calibration
# Requirements: 73-REQ-3.1
# ---------------------------------------------------------------------------


class TestSeverityCalibration:
    """Merged findings get a calibrated severity from the critic."""

    @pytest.mark.asyncio
    async def test_merged_group_gets_calibrated_severity(self) -> None:
        """Critic assigns 'critical' severity to the merged group of minor+major."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(title="Minor issue", severity="minor", group_key="a")
        finding_b = _make_finding(title="Major issue", severity="major", group_key="b")
        finding_c = _make_finding(title="Info issue", severity="info", group_key="c")

        mock_response = _make_critic_response(
            groups=[
                {
                    "title": "Critical merged issue",
                    "description": "Combined context reveals critical severity.",
                    "severity": "critical",
                    "finding_indices": [0, 1],
                    "merge_reason": "Related findings escalate to critical",
                },
                {
                    "title": "Info issue",
                    "description": "Standalone info finding.",
                    "severity": "info",
                    "finding_indices": [2],
                    "merge_reason": "Standalone",
                },
            ]
        )

        with patch(
            "agent_fox.nightshift.critic._run_critic",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            groups = await consolidate_findings([finding_a, finding_b, finding_c])  # type: ignore[list-item]

        merged_group = next(g for g in groups if len(g.findings) > 1)
        # Calibrated severity must appear in the body or as a dedicated field
        assert "critical" in merged_group.body or getattr(merged_group, "severity", None) == "critical"

    @pytest.mark.asyncio
    async def test_standalone_severity_info_in_body(self) -> None:
        """Standalone finding C retains its 'info' severity in the group body."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(severity="minor", group_key="a")
        finding_b = _make_finding(severity="major", group_key="b")
        finding_c = _make_finding(severity="info", group_key="c")

        mock_response = _make_critic_response(
            groups=[
                {
                    "title": "Merged",
                    "description": "Merged description.",
                    "severity": "critical",
                    "finding_indices": [0, 1],
                    "merge_reason": "Related",
                },
                {
                    "title": "Info finding",
                    "description": "Info level standalone.",
                    "severity": "info",
                    "finding_indices": [2],
                    "merge_reason": "Standalone",
                },
            ]
        )

        with patch(
            "agent_fox.nightshift.critic._run_critic",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            groups = await consolidate_findings([finding_a, finding_b, finding_c])  # type: ignore[list-item]

        standalone = next(g for g in groups if len(g.findings) == 1)
        assert "info" in standalone.body


# ---------------------------------------------------------------------------
# TS-73-9: Output compatibility
# Requirements: 73-REQ-5.1, 73-REQ-5.2, 73-REQ-5.3
# ---------------------------------------------------------------------------


class TestOutputCompatibility:
    """Critic output is compatible with create_issues_from_groups()."""

    @pytest.mark.asyncio
    async def test_all_groups_have_required_fields(self) -> None:
        """Every FindingGroup has non-empty title, body, and findings list."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings
        from agent_fox.nightshift.finding import Finding

        finding_a = _make_finding(title="Finding A", group_key="a")
        finding_b = _make_finding(title="Finding B", group_key="b")
        finding_c = _make_finding(title="Finding C", group_key="c")

        mock_response = _make_critic_response(
            groups=[
                {
                    "title": "Group title A",
                    "description": "Group A description",
                    "severity": "minor",
                    "finding_indices": [0],
                    "merge_reason": "Standalone",
                },
                {
                    "title": "Group title B",
                    "description": "Group B description",
                    "severity": "minor",
                    "finding_indices": [1],
                    "merge_reason": "Standalone",
                },
                {
                    "title": "Group title C",
                    "description": "Group C description",
                    "severity": "minor",
                    "finding_indices": [2],
                    "merge_reason": "Standalone",
                },
            ]
        )

        with patch(
            "agent_fox.nightshift.critic._run_critic",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            groups = await consolidate_findings([finding_a, finding_b, finding_c])  # type: ignore[list-item]

        for g in groups:
            assert g.title != ""
            assert g.body != ""
            assert len(g.findings) > 0
            assert all(isinstance(f, Finding) for f in g.findings)


# ---------------------------------------------------------------------------
# TS-73-E1: All findings share same root cause
# Requirements: 73-REQ-1.E1
# ---------------------------------------------------------------------------


class TestAllSameRootCause:
    """All findings merge into a single group when sharing root cause."""

    @pytest.mark.asyncio
    async def test_all_merged_into_one_group(self) -> None:
        """All three findings merge into one FindingGroup."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(title="Unused auth helper A", group_key="a")
        finding_b = _make_finding(title="Unused auth helper B", group_key="b")
        finding_c = _make_finding(title="Unused auth helper C", group_key="c")

        mock_response = _make_critic_response(
            groups=[
                {
                    "title": "All auth helper issues combined",
                    "description": "All three findings flag the same root cause.",
                    "severity": "major",
                    "finding_indices": [0, 1, 2],
                    "merge_reason": "All three findings flag the same auth module",
                }
            ]
        )

        with patch(
            "agent_fox.nightshift.critic._run_critic",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            groups = await consolidate_findings([finding_a, finding_b, finding_c])  # type: ignore[list-item]

        assert len(groups) == 1
        assert len(groups[0].findings) == 3


# ---------------------------------------------------------------------------
# TS-73-E2: No shared root cause
# Requirements: 73-REQ-1.E2
# ---------------------------------------------------------------------------


class TestNoSharedRootCause:
    """Each finding becomes its own group when nothing shares a root cause."""

    @pytest.mark.asyncio
    async def test_no_merge_three_groups(self) -> None:
        """Three unrelated findings produce three FindingGroups."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(title="Finding A", group_key="a")
        finding_b = _make_finding(title="Finding B", group_key="b")
        finding_c = _make_finding(title="Finding C", group_key="c")

        mock_response = _make_critic_response(
            groups=[
                {
                    "title": "Finding A",
                    "description": "Standalone A",
                    "severity": "minor",
                    "finding_indices": [0],
                    "merge_reason": "Standalone",
                },
                {
                    "title": "Finding B",
                    "description": "Standalone B",
                    "severity": "minor",
                    "finding_indices": [1],
                    "merge_reason": "Standalone",
                },
                {
                    "title": "Finding C",
                    "description": "Standalone C",
                    "severity": "minor",
                    "finding_indices": [2],
                    "merge_reason": "Standalone",
                },
            ]
        )

        with patch(
            "agent_fox.nightshift.critic._run_critic",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            groups = await consolidate_findings([finding_a, finding_b, finding_c])  # type: ignore[list-item]

        assert len(groups) == 3


# ---------------------------------------------------------------------------
# TS-73-E3: All findings dropped
# Requirements: 73-REQ-2.E1
# ---------------------------------------------------------------------------


class TestAllFindingsDropped:
    """Critic drops all findings; empty list is returned."""

    @pytest.mark.asyncio
    async def test_all_dropped_returns_empty_list(self) -> None:
        """When all findings are dropped, consolidate_findings returns []."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(title="Finding A", evidence="", group_key="a")
        finding_b = _make_finding(title="Finding B", evidence="", group_key="b")
        finding_c = _make_finding(title="Finding C", evidence="", group_key="c")

        mock_response = _make_critic_response(
            groups=[],
            dropped=[
                {"finding_index": 0, "reason": "Evidence field is empty"},
                {"finding_index": 1, "reason": "Evidence field is empty"},
                {"finding_index": 2, "reason": "Evidence field is empty"},
            ],
        )

        with patch(
            "agent_fox.nightshift.critic._run_critic",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            groups = await consolidate_findings([finding_a, finding_b, finding_c])  # type: ignore[list-item]

        assert groups == []


# ---------------------------------------------------------------------------
# TS-73-E4: Speculative evidence dropped
# Requirements: 73-REQ-2.E2
# ---------------------------------------------------------------------------


class TestSpeculativeEvidenceDropped:
    """Finding with speculative evidence ('might be') is dropped."""

    @pytest.mark.asyncio
    async def test_speculative_evidence_dropped(self) -> None:
        """Finding A with 'might be' evidence is dropped; B and C are retained."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(
            title="Speculative finding",
            evidence="This might be a problem",
            group_key="a",
        )
        finding_b = _make_finding(
            title="Finding B",
            evidence="ruff: F401 auth.py:1",
            group_key="b",
        )
        finding_c = _make_finding(
            title="Finding C",
            evidence="coverage: 12% payments.py",
            group_key="c",
        )

        mock_response = _make_critic_response(
            groups=[
                {
                    "title": "Finding B",
                    "description": "Concrete finding B",
                    "severity": "minor",
                    "finding_indices": [1],
                    "merge_reason": "Standalone",
                },
                {
                    "title": "Finding C",
                    "description": "Concrete finding C",
                    "severity": "minor",
                    "finding_indices": [2],
                    "merge_reason": "Standalone",
                },
            ],
            dropped=[
                {
                    "finding_index": 0,
                    "reason": "Evidence is speculative: 'might be a problem'",
                }
            ],
        )

        with patch(
            "agent_fox.nightshift.critic._run_critic",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            groups = await consolidate_findings([finding_a, finding_b, finding_c])  # type: ignore[list-item]

        all_findings = [f for g in groups for f in g.findings]
        assert finding_a not in all_findings
        assert len(all_findings) == 2


# ---------------------------------------------------------------------------
# TS-73-E5: Severity preserved when not merged
# Requirements: 73-REQ-3.E1
# ---------------------------------------------------------------------------


class TestSeverityPreservedWhenNotMerged:
    """Standalone finding keeps its original severity."""

    @pytest.mark.asyncio
    async def test_standalone_severity_preserved(self) -> None:
        """Standalone finding with severity='minor' retains it in the group body."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(title="Minor standalone", severity="minor", group_key="a")
        finding_b = _make_finding(title="Finding B to merge", severity="major", group_key="b")
        finding_c = _make_finding(title="Finding C to merge", severity="major", group_key="c")

        mock_response = _make_critic_response(
            groups=[
                {
                    "title": "Minor standalone",
                    "description": "This finding is standalone with original severity.",
                    "severity": "minor",
                    "finding_indices": [0],
                    "merge_reason": "Standalone",
                },
                {
                    "title": "Merged B and C",
                    "description": "B and C are related.",
                    "severity": "major",
                    "finding_indices": [1, 2],
                    "merge_reason": "Same root cause",
                },
            ]
        )

        with patch(
            "agent_fox.nightshift.critic._run_critic",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            groups = await consolidate_findings([finding_a, finding_b, finding_c])  # type: ignore[list-item]

        standalone = next(g for g in groups if len(g.findings) == 1)
        assert "minor" in standalone.body


# ---------------------------------------------------------------------------
# TS-73-E7: Malformed AI response triggers mechanical fallback
# Requirements: 73-REQ-5.E1, 73-REQ-6.E1
# ---------------------------------------------------------------------------


class TestMalformedJsonFallback:
    """Malformed JSON response triggers mechanical grouping fallback."""

    @pytest.mark.asyncio
    async def test_malformed_json_falls_back_to_mechanical(self, caplog: pytest.LogCaptureFixture) -> None:
        """Invalid JSON response causes fallback: three groups for three findings."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(title="Finding A", group_key="a")
        finding_b = _make_finding(title="Finding B", group_key="b")
        finding_c = _make_finding(title="Finding C", group_key="c")

        with (
            patch(
                "agent_fox.nightshift.critic._run_critic",
                new_callable=AsyncMock,
                return_value="this is not valid JSON {{{",
            ),
            caplog.at_level(logging.WARNING),
        ):
            groups = await consolidate_findings([finding_a, finding_b, finding_c])  # type: ignore[list-item]

        # Mechanical fallback: one group per finding
        assert len(groups) == 3
        # Warning logged about malformed response
        assert any(
            "malformed" in r.message.lower() or "fallback" in r.message.lower() or "invalid" in r.message.lower()
            for r in caplog.records
            if r.levelno == logging.WARNING
        )


# ---------------------------------------------------------------------------
# TS-73-E9: AI backend unavailable triggers mechanical fallback
# Requirements: 73-REQ-7.E1
# ---------------------------------------------------------------------------


class TestAiBackendFailure:
    """AI backend failure triggers mechanical grouping fallback."""

    @pytest.mark.asyncio
    async def test_backend_exception_falls_back_to_mechanical(self, caplog: pytest.LogCaptureFixture) -> None:
        """AI backend exception causes fallback: three groups for three findings."""
        from unittest.mock import AsyncMock, patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(title="Finding A", group_key="a")
        finding_b = _make_finding(title="Finding B", group_key="b")
        finding_c = _make_finding(title="Finding C", group_key="c")

        with (
            patch(
                "agent_fox.nightshift.critic._run_critic",
                new_callable=AsyncMock,
                side_effect=RuntimeError("AI backend is unavailable"),
            ),
            caplog.at_level(logging.WARNING),
        ):
            groups = await consolidate_findings([finding_a, finding_b, finding_c])  # type: ignore[list-item]

        # Mechanical fallback: one group per finding
        assert len(groups) == 3
        # Warning logged about backend failure
        assert any(
            "fallback" in r.message.lower() or "unavailable" in r.message.lower() or "failed" in r.message.lower()
            for r in caplog.records
            if r.levelno == logging.WARNING
        )
