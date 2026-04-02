"""Unit tests for the finding consolidation critic.

Test Spec: TS-73-2, TS-73-5, TS-73-7, TS-73-8, TS-73-10, TS-73-11, TS-73-E6, TS-73-E8
Requirements: 73-REQ-1.2, 73-REQ-2.3, 73-REQ-3.2, 73-REQ-4.1, 73-REQ-4.2, 73-REQ-4.E1,
              73-REQ-5.E2, 73-REQ-6.3, 73-REQ-7.1, 73-REQ-7.2, 73-REQ-7.3
"""

from __future__ import annotations

import inspect
import json
import logging

import pytest


def _make_finding(**overrides: object) -> object:
    """Create a Finding with sensible defaults, overridden as needed."""
    from agent_fox.nightshift.finding import Finding

    defaults: dict[str, object] = {
        "category": "linter_debt",
        "title": "Unused imports",
        "description": "5 files contain unused imports.",
        "severity": "minor",
        "affected_files": ["agent_fox/engine.py"],
        "suggested_fix": "Remove unused imports using ruff --fix",
        "evidence": "ruff: F401 engine.py:1",
        "group_key": "unused-imports",
    }
    defaults.update(overrides)
    return Finding(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TS-73-11: Async signature introspection
# Requirements: 73-REQ-7.1, 73-REQ-7.2, 73-REQ-7.3
# ---------------------------------------------------------------------------


class TestAsyncSignature:
    """consolidate_findings is async with the correct signature."""

    def test_is_coroutine_function(self) -> None:
        """consolidate_findings must be an async (coroutine) function."""
        from agent_fox.nightshift.critic import consolidate_findings

        assert inspect.iscoroutinefunction(consolidate_findings)

    def test_has_findings_parameter(self) -> None:
        """consolidate_findings must accept a 'findings' parameter."""
        from agent_fox.nightshift.critic import consolidate_findings

        sig = inspect.signature(consolidate_findings)
        assert "findings" in sig.parameters


# ---------------------------------------------------------------------------
# TS-73-8: Below-threshold mechanical grouping
# Requirements: 73-REQ-4.1, 73-REQ-4.2
# ---------------------------------------------------------------------------


class TestBelowThresholdMechanicalGrouping:
    """Fewer than 3 findings skip the AI critic and use mechanical grouping."""

    @pytest.mark.asyncio
    async def test_two_findings_skip_ai(self) -> None:
        """Two findings produce two groups without calling the AI backend."""
        from unittest.mock import patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(title="Finding A", group_key="a")
        finding_b = _make_finding(title="Finding B", group_key="b")

        with patch("agent_fox.nightshift.critic._run_critic") as ai_mock:
            groups = await consolidate_findings([finding_a, finding_b])

        assert len(groups) == 2
        assert ai_mock.call_count == 0

    @pytest.mark.asyncio
    async def test_two_findings_each_own_group(self) -> None:
        """Each finding below threshold becomes its own FindingGroup."""
        from agent_fox.nightshift.critic import consolidate_findings

        finding_a = _make_finding(title="Finding A", group_key="a")
        finding_b = _make_finding(title="Finding B", group_key="b")

        groups = await consolidate_findings([finding_a, finding_b])

        assert len(groups) == 2
        group_findings_lists = [g.findings for g in groups]
        assert [finding_a] in group_findings_lists
        assert [finding_b] in group_findings_lists

    @pytest.mark.asyncio
    async def test_one_finding_mechanical(self) -> None:
        """A single finding also uses mechanical grouping, producing one group."""
        from unittest.mock import patch

        from agent_fox.nightshift.critic import consolidate_findings

        finding = _make_finding(title="Solo Finding")

        with patch("agent_fox.nightshift.critic._run_critic") as ai_mock:
            groups = await consolidate_findings([finding])

        assert len(groups) == 1
        assert groups[0].findings == [finding]
        assert ai_mock.call_count == 0


# ---------------------------------------------------------------------------
# TS-73-E6: Zero findings
# Requirements: 73-REQ-4.E1
# ---------------------------------------------------------------------------


class TestZeroFindings:
    """Empty input returns empty output immediately."""

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_list(self) -> None:
        """consolidate_findings([]) returns [] without making any AI call."""
        from unittest.mock import patch

        from agent_fox.nightshift.critic import consolidate_findings

        with patch("agent_fox.nightshift.critic._run_critic") as ai_mock:
            groups = await consolidate_findings([])

        assert groups == []
        assert ai_mock.call_count == 0


# ---------------------------------------------------------------------------
# TS-73-2: Affected files union
# Requirements: 73-REQ-1.2
# ---------------------------------------------------------------------------


class TestAffectedFilesUnion:
    """Merged FindingGroup has sorted, deduplicated union of affected files."""

    def test_union_of_affected_files(self) -> None:
        """Merged group's affected_files is the sorted, deduplicated union."""
        from agent_fox.nightshift.critic import _parse_critic_response

        finding_a = _make_finding(affected_files=["auth.py", "utils.py"])
        finding_b = _make_finding(affected_files=["auth.py", "middleware.py"])

        response = json.dumps(
            {
                "groups": [
                    {
                        "title": "Combined auth issues",
                        "description": "Auth-related issues affecting multiple files",
                        "severity": "major",
                        "finding_indices": [0, 1],
                        "merge_reason": "Same auth module",
                    }
                ],
                "dropped": [],
            }
        )

        groups, _ = _parse_critic_response(response, [finding_a, finding_b])
        assert len(groups) == 1
        assert groups[0].affected_files == ["auth.py", "middleware.py", "utils.py"]

    def test_deduplication_of_affected_files(self) -> None:
        """Duplicate file paths appear only once in merged group's affected_files."""
        from agent_fox.nightshift.critic import _parse_critic_response

        finding_a = _make_finding(affected_files=["auth.py"])
        finding_b = _make_finding(affected_files=["auth.py"])

        response = json.dumps(
            {
                "groups": [
                    {
                        "title": "Auth issues",
                        "description": "Auth-related issues",
                        "severity": "minor",
                        "finding_indices": [0, 1],
                        "merge_reason": "Same file",
                    }
                ],
                "dropped": [],
            }
        )

        groups, _ = _parse_critic_response(response, [finding_a, finding_b])
        assert len(groups) == 1
        assert groups[0].affected_files == ["auth.py"]


# ---------------------------------------------------------------------------
# TS-73-E8: Invalid finding indices
# Requirements: 73-REQ-5.E2
# ---------------------------------------------------------------------------


class TestInvalidFindingIndices:
    """Out-of-bounds indices in AI response are ignored with a warning."""

    def test_out_of_bounds_index_ignored(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Index 99 is ignored; group is built only from valid indices 0 and 1."""
        from agent_fox.nightshift.critic import _parse_critic_response

        finding_a = _make_finding(title="Finding A")
        finding_b = _make_finding(title="Finding B")
        finding_c = _make_finding(title="Finding C")

        response = json.dumps(
            {
                "groups": [
                    {
                        "title": "Valid merged group",
                        "description": "Merged description for related issues",
                        "severity": "major",
                        "finding_indices": [0, 1, 99],
                        "merge_reason": "Related issues",
                    }
                ],
                "dropped": [],
            }
        )

        with caplog.at_level(logging.WARNING):
            groups, _ = _parse_critic_response(
                response, [finding_a, finding_b, finding_c]
            )

        # Only valid-indexed findings are included; index 99 is skipped
        all_grouped_findings = [f for g in groups for f in g.findings]
        assert all(f in [finding_a, finding_b] for f in all_grouped_findings)
        # Warning must be logged about the out-of-bounds index
        assert any(
            "out of bounds" in r.message.lower() or "invalid" in r.message.lower()
            for r in caplog.records
        )


# ---------------------------------------------------------------------------
# TS-73-5: Drop logged at INFO
# Requirements: 73-REQ-2.3, 73-REQ-6.1, 73-REQ-6.2
# ---------------------------------------------------------------------------


class TestDropLogged:
    """Dropped findings are logged with action and reason at INFO level."""

    def test_drop_decision_logged_at_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A 'dropped' decision is logged at INFO with its reason."""
        from agent_fox.nightshift.critic import (
            CriticDecision,
            CriticSummary,
            _log_decisions,
        )

        decision = CriticDecision(
            action="dropped",
            finding_indices=[1],
            reason="Evidence field is empty",
            original_severity=None,
            new_severity=None,
        )
        summary = CriticSummary(
            total_received=3,
            total_dropped=1,
            total_merged=0,
            groups_produced=2,
        )

        with caplog.at_level(logging.INFO, logger="agent_fox"):
            _log_decisions([decision], summary)

        assert any(
            "dropped" in r.message and "Evidence field is empty" in r.message
            for r in caplog.records
            if r.levelno == logging.INFO
        )


# ---------------------------------------------------------------------------
# TS-73-7: Severity change logged
# Requirements: 73-REQ-3.2
# ---------------------------------------------------------------------------


class TestSeverityChangeLogged:
    """Severity changes are logged with original and new severity at INFO."""

    def test_severity_change_logged_with_values(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A 'severity_changed' decision logs original and new severity."""
        from agent_fox.nightshift.critic import (
            CriticDecision,
            CriticSummary,
            _log_decisions,
        )

        decision = CriticDecision(
            action="severity_changed",
            finding_indices=[0],
            reason="Multiple categories flag same critical path",
            original_severity="minor",
            new_severity="critical",
        )
        summary = CriticSummary(
            total_received=3,
            total_dropped=0,
            total_merged=0,
            groups_produced=3,
        )

        with caplog.at_level(logging.INFO, logger="agent_fox"):
            _log_decisions([decision], summary)

        assert any(
            "minor" in r.message and "critical" in r.message
            for r in caplog.records
            if r.levelno == logging.INFO
        )


# ---------------------------------------------------------------------------
# TS-73-10: Summary log
# Requirements: 73-REQ-6.3, 73-REQ-6.4
# ---------------------------------------------------------------------------


class TestSummaryLog:
    """Critic logs a summary with all four counts at INFO level."""

    def test_summary_contains_counts(self, caplog: pytest.LogCaptureFixture) -> None:
        """Summary log contains total received count and 'dropped' keyword."""
        from agent_fox.nightshift.critic import CriticSummary, _log_decisions

        summary = CriticSummary(
            total_received=5,
            total_dropped=1,
            total_merged=3,
            groups_produced=2,
        )

        with caplog.at_level(logging.INFO, logger="agent_fox"):
            _log_decisions([], summary)

        assert any(
            "5" in r.message and "dropped" in r.message
            for r in caplog.records
            if r.levelno == logging.INFO
        )

    def test_summary_contains_groups_produced(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Summary log mentions the number of groups produced."""
        from agent_fox.nightshift.critic import CriticSummary, _log_decisions

        summary = CriticSummary(
            total_received=5,
            total_dropped=1,
            total_merged=3,
            groups_produced=2,
        )

        with caplog.at_level(logging.INFO, logger="agent_fox"):
            _log_decisions([], summary)

        # All four summary values should appear somewhere in the INFO logs
        info_messages = " ".join(
            r.message for r in caplog.records if r.levelno == logging.INFO
        )
        assert "5" in info_messages  # total_received
        assert "1" in info_messages  # total_dropped
        assert "2" in info_messages  # groups_produced
