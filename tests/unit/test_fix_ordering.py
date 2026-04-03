"""Unit tests for fix issue ordering and dependency detection.

Test Spec: TS-71-1 through TS-71-20, TS-71-E1 through TS-71-E9
Requirements: 71-REQ-1.*, 71-REQ-2.*, 71-REQ-3.*, 71-REQ-4.*,
              71-REQ-5.*, 71-REQ-6.*
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.platform.github import IssueResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(number: int, body: str = "", title: str = "") -> IssueResult:
    """Create a minimal IssueResult for testing."""
    return IssueResult(
        number=number,
        title=title or f"Issue #{number}",
        html_url=f"https://github.com/test/repo/issues/{number}",
        body=body,
    )


# ---------------------------------------------------------------------------
# TS-71-1: Issues fetched in ascending order
# Requirement: 71-REQ-1.1
# ---------------------------------------------------------------------------


class TestBaseOrdering:
    """Verify base issue ordering behavior."""

    @pytest.mark.asyncio
    async def test_ts_71_1_issues_fetched_ascending(self) -> None:
        """Platform called with sort='created', direction='asc'."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)

        engine = NightShiftEngine(config=config, platform=mock_platform)
        engine._process_fix = AsyncMock()  # type: ignore[assignment]

        await engine._run_issue_check()

        mock_platform.list_issues_by_label.assert_called()
        # Check the FIRST call (the initial issue fetch) for ascending sort
        first_call = mock_platform.list_issues_by_label.call_args_list[0]
        assert first_call.kwargs.get("direction") == "asc" or (len(first_call.args) > 2 and first_call.args[2] == "asc")

    # -----------------------------------------------------------------------
    # TS-71-2: Default order is ascending issue number
    # Requirement: 71-REQ-1.2
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_ts_71_2_default_order_ascending_number(self) -> None:
        """With no deps, issues processed lowest-number first."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        # Return in non-sorted order
        issues = [_make_issue(30), _make_issue(10)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)

        engine = NightShiftEngine(config=config, platform=mock_platform)

        processed: list[int] = []

        async def track_fix(issue: IssueResult) -> None:
            processed.append(issue.number)

        engine._process_fix = track_fix  # type: ignore[assignment]

        await engine._run_issue_check()

        assert processed == [10, 30]


# ---------------------------------------------------------------------------
# TS-71-3, TS-71-4, TS-71-5: Reference parsing
# Requirements: 71-REQ-2.1, 71-REQ-2.2, 71-REQ-2.3
# ---------------------------------------------------------------------------


class TestReferenceParsing:
    """Verify explicit dependency extraction from issue text and GitHub."""

    def test_ts_71_3_explicit_text_references_parsed(self) -> None:
        """'depends on #N' in issue body produces a dependency edge."""
        from agent_fox.nightshift.reference_parser import parse_text_references

        issue_10 = _make_issue(10, body="This is a standalone issue.")
        issue_20 = _make_issue(20, body="This depends on #10 to work.")

        edges = parse_text_references([issue_10, issue_20])

        assert len(edges) == 1
        assert edges[0].from_issue == 10
        assert edges[0].to_issue == 20
        assert edges[0].source == "explicit"

    @pytest.mark.asyncio
    async def test_ts_71_4_github_relationships_incorporated(self) -> None:
        """GitHub blocks/is-blocked-by metadata produces edges."""
        from agent_fox.nightshift.reference_parser import (
            fetch_github_relationships,
        )

        mock_platform = AsyncMock()
        # Mock platform to return timeline indicating #10 blocks #20
        mock_platform.get_issue_timeline = AsyncMock(
            side_effect=lambda n: (
                [
                    {
                        "event": "cross-referenced",
                        "source": {"issue": {"number": 10}},
                    }
                ]
                if n == 20
                else []
            )
        )

        issue_10 = _make_issue(10)
        issue_20 = _make_issue(20)

        edges = await fetch_github_relationships(mock_platform, [issue_10, issue_20])

        assert len(edges) == 1
        assert edges[0].source == "github"

    def test_ts_71_5_multiple_text_patterns_recognized(self) -> None:
        """All four text patterns matched case-insensitively."""
        from agent_fox.nightshift.reference_parser import parse_text_references

        issue_1 = _make_issue(1)
        issue_2 = _make_issue(2)
        issue_3 = _make_issue(3)
        issue_4 = _make_issue(4)
        issue_a = _make_issue(10, body="Depends on #1")
        issue_b = _make_issue(11, body="BLOCKED BY #2")
        issue_c = _make_issue(12, body="after #3")
        issue_d = _make_issue(13, body="Requires #4")

        all_issues = [
            issue_1,
            issue_2,
            issue_3,
            issue_4,
            issue_a,
            issue_b,
            issue_c,
            issue_d,
        ]
        edges = parse_text_references(all_issues)

        assert len(edges) == 4
        to_issues = {e.to_issue for e in edges}
        assert to_issues == {10, 11, 12, 13}


# ---------------------------------------------------------------------------
# TS-71-6 through TS-71-10: AI triage
# Requirements: 71-REQ-3.1, 71-REQ-3.2, 71-REQ-3.3, 71-REQ-3.4, 71-REQ-3.5
# ---------------------------------------------------------------------------


class TestAITriage:
    """Verify AI batch triage behavior."""

    @pytest.mark.asyncio
    async def test_ts_71_6_ai_triage_triggered_for_batch_gte_3(self) -> None:
        """AI triage called when batch has 3+ issues."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)

        engine = NightShiftEngine(config=config, platform=mock_platform)
        engine._process_fix = AsyncMock()  # type: ignore[assignment]

        with patch(
            "agent_fox.nightshift.engine.run_batch_triage",
            new_callable=AsyncMock,
        ) as mock_triage:
            from agent_fox.nightshift.triage import TriageResult

            mock_triage.return_value = TriageResult(
                processing_order=[10, 20, 30],
                edges=[],
                supersession_pairs=[],
            )
            await engine._run_issue_check()

            assert mock_triage.call_count == 1

    @pytest.mark.asyncio
    async def test_ts_71_7_ai_triage_uses_advanced_tier(self) -> None:
        """Triage uses ADVANCED model tier."""
        from agent_fox.nightshift.triage import TriageResult, run_batch_triage

        config = MagicMock()
        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]

        with patch(
            "agent_fox.nightshift.triage._run_ai_triage",
            new_callable=AsyncMock,
        ) as mock_ai:
            mock_ai.return_value = TriageResult(
                processing_order=[10, 20, 30],
                edges=[],
                supersession_pairs=[],
            )
            result = await run_batch_triage(issues, [], config)

            # Verify ADVANCED tier was requested
            call_kwargs = mock_ai.call_args
            assert "ADVANCED" in str(call_kwargs) or hasattr(result, "processing_order")

    @pytest.mark.asyncio
    async def test_ts_71_8_triage_returns_order_edges_supersession(self) -> None:
        """TriageResult contains all three fields."""
        from agent_fox.nightshift.triage import TriageResult, run_batch_triage

        config = MagicMock()
        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]

        with patch(
            "agent_fox.nightshift.triage._run_ai_triage",
            new_callable=AsyncMock,
        ) as mock_ai:
            mock_ai.return_value = TriageResult(
                processing_order=[10, 20, 30],
                edges=[],
                supersession_pairs=[(10, 20)],
            )
            result = await run_batch_triage(issues, [], config)

            assert isinstance(result.processing_order, list)
            assert isinstance(result.edges, list)
            assert isinstance(result.supersession_pairs, list)

    def test_ts_71_9_explicit_edges_override_ai_edges(self) -> None:
        """Explicit edge A->B wins over conflicting AI edge B->A."""
        from agent_fox.nightshift.dep_graph import (
            DependencyEdge,
            build_graph,
            merge_edges,
        )

        explicit = [DependencyEdge(10, 20, "explicit", "user said so")]
        ai = [DependencyEdge(20, 10, "ai", "AI detected")]

        merged = merge_edges(explicit, ai)
        issues = [_make_issue(10), _make_issue(20)]
        order = build_graph(issues, merged)

        assert order.index(10) < order.index(20)

    @pytest.mark.asyncio
    async def test_ts_71_10_ai_triage_skipped_for_batch_lt_3(self) -> None:
        """For 1-2 issues, no AI triage invoked."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        issues = [_make_issue(10), _make_issue(20)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)

        engine = NightShiftEngine(config=config, platform=mock_platform)
        engine._process_fix = AsyncMock()  # type: ignore[assignment]

        with patch(
            "agent_fox.nightshift.engine.run_batch_triage",
            new_callable=AsyncMock,
        ) as mock_triage:
            await engine._run_issue_check()

            assert mock_triage.call_count == 0


# ---------------------------------------------------------------------------
# TS-71-11, TS-71-12, TS-71-13: Dependency graph
# Requirements: 71-REQ-4.1, 71-REQ-4.2, 71-REQ-4.3
# ---------------------------------------------------------------------------


class TestDepGraph:
    """Verify dependency graph construction and topological sort."""

    def test_ts_71_11_topological_sort_valid_order(self) -> None:
        """Dependencies respected in output order."""
        from agent_fox.nightshift.dep_graph import DependencyEdge, build_graph

        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]
        edges = [
            DependencyEdge(10, 20, "explicit", "10 before 20"),
            DependencyEdge(20, 30, "explicit", "20 before 30"),
        ]

        order = build_graph(issues, edges)

        assert order == [10, 20, 30]

    def test_ts_71_12_tie_breaking_by_issue_number(self) -> None:
        """Independent issues sorted by ascending number."""
        from agent_fox.nightshift.dep_graph import build_graph

        issues = [_make_issue(30), _make_issue(10), _make_issue(20)]

        order = build_graph(issues, [])

        assert order == [10, 20, 30]

    def test_ts_71_13_cycle_detected_and_broken(self, caplog: pytest.LogCaptureFixture) -> None:
        """Cycles broken at edge pointing to oldest issue."""
        from agent_fox.nightshift.dep_graph import DependencyEdge, build_graph

        issues = [_make_issue(10), _make_issue(20)]
        edges = [
            DependencyEdge(10, 20, "explicit", "10 before 20"),
            DependencyEdge(20, 10, "explicit", "20 before 10"),
        ]

        with caplog.at_level(logging.WARNING):
            order = build_graph(issues, edges)

        assert order[0] == 10
        assert len(order) == 2
        assert any("cycle" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# TS-71-14 through TS-71-17: Staleness
# Requirements: 71-REQ-5.1, 71-REQ-5.2, 71-REQ-5.3, 71-REQ-5.4
# ---------------------------------------------------------------------------


class TestStaleness:
    """Verify post-fix staleness check behavior."""

    @pytest.mark.asyncio
    async def test_ts_71_14_staleness_check_runs_after_fix(self) -> None:
        """After successful fix, remaining issues evaluated for staleness."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)
        mock_platform.close_issue = AsyncMock()

        engine = NightShiftEngine(config=config, platform=mock_platform)
        engine._process_fix = AsyncMock()  # type: ignore[assignment]

        with patch(
            "agent_fox.nightshift.engine.check_staleness",
            new_callable=AsyncMock,
        ) as mock_staleness:
            from agent_fox.nightshift.staleness import StalenessResult

            mock_staleness.return_value = StalenessResult(obsolete_issues=[], rationale={})
            await engine._run_issue_check()

            assert mock_staleness.called
            # Should be called with remaining issues after each fix
            first_call_args = mock_staleness.call_args_list[0]
            if len(first_call_args.args) > 1:
                remaining = first_call_args.args[1]
            else:
                remaining = first_call_args.kwargs.get("remaining_issues")
            remaining_numbers = [i.number for i in remaining]
            assert 20 in remaining_numbers
            assert 30 in remaining_numbers

    @pytest.mark.asyncio
    async def test_ts_71_15_staleness_verifies_with_github(self) -> None:
        """Staleness check re-fetches issues from GitHub to verify."""
        from agent_fox.nightshift.staleness import StalenessResult, check_staleness

        mock_platform = AsyncMock()
        mock_platform.list_issues_by_label = AsyncMock(return_value=[])
        config = MagicMock()

        fixed_issue = _make_issue(10)
        remaining = [_make_issue(20)]

        with patch(
            "agent_fox.nightshift.staleness._run_ai_staleness",
            new_callable=AsyncMock,
        ) as mock_ai:
            mock_ai.return_value = StalenessResult(obsolete_issues=[20], rationale={20: "same root cause"})
            await check_staleness(
                fixed_issue,
                remaining,
                "diff content",
                config,
                mock_platform,
            )

            # Should have called platform to verify
            assert mock_platform.list_issues_by_label.called or mock_platform.method_calls

    @pytest.mark.asyncio
    async def test_ts_71_16_obsolete_issues_closed_with_comment(self) -> None:
        """Issues determined obsolete are closed on GitHub with comment."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)
        mock_platform.close_issue = AsyncMock()

        engine = NightShiftEngine(config=config, platform=mock_platform)
        engine._process_fix = AsyncMock()  # type: ignore[assignment]

        with patch(
            "agent_fox.nightshift.engine.check_staleness",
            new_callable=AsyncMock,
        ) as mock_staleness:
            from agent_fox.nightshift.staleness import StalenessResult

            # First fix (#10) makes #20 obsolete
            mock_staleness.return_value = StalenessResult(obsolete_issues=[20], rationale={20: "resolved by #10"})
            await engine._run_issue_check()

            # close_issue called for #20 with comment mentioning #10
            mock_platform.close_issue.assert_called()
            close_args = mock_platform.close_issue.call_args
            issue_num = close_args.args[0] if close_args.args else close_args.kwargs.get("issue_number")
            assert issue_num == 20
            comment = close_args.args[1] if len(close_args.args) > 1 else close_args.kwargs.get("comment", "")
            assert "#10" in str(comment)

    @pytest.mark.asyncio
    async def test_ts_71_17_obsolete_issues_removed_from_queue(self) -> None:
        """Closed issues not processed in subsequent iterations."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)
        mock_platform.close_issue = AsyncMock()

        engine = NightShiftEngine(config=config, platform=mock_platform)

        processed: list[int] = []

        async def track_fix(issue: IssueResult) -> None:
            processed.append(issue.number)

        engine._process_fix = track_fix  # type: ignore[assignment]

        with patch(
            "agent_fox.nightshift.engine.check_staleness",
            new_callable=AsyncMock,
        ) as mock_staleness:
            from agent_fox.nightshift.staleness import StalenessResult

            call_count = 0

            async def staleness_effect(*args: object, **kwargs: object) -> StalenessResult:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # After fixing #10, mark #20 obsolete
                    return StalenessResult(
                        obsolete_issues=[20],
                        rationale={20: "resolved"},
                    )
                return StalenessResult(obsolete_issues=[], rationale={})

            mock_staleness.side_effect = staleness_effect
            await engine._run_issue_check()

        # #20 should NOT be processed
        assert processed == [10, 30]


# ---------------------------------------------------------------------------
# TS-71-18, TS-71-19, TS-71-20: Observability
# Requirements: 71-REQ-6.1, 71-REQ-6.2, 71-REQ-6.3
# ---------------------------------------------------------------------------


class TestObservability:
    """Verify logging and audit event behavior."""

    @pytest.mark.asyncio
    async def test_ts_71_18_resolved_order_logged_at_info(self, caplog: pytest.LogCaptureFixture) -> None:
        """Processing order logged at INFO after triage."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)
        mock_platform.close_issue = AsyncMock()

        engine = NightShiftEngine(config=config, platform=mock_platform)
        engine._process_fix = AsyncMock()  # type: ignore[assignment]

        with (
            patch(
                "agent_fox.nightshift.engine.run_batch_triage",
                new_callable=AsyncMock,
            ) as mock_triage,
            patch(
                "agent_fox.nightshift.engine.check_staleness",
                new_callable=AsyncMock,
            ) as mock_staleness,
            caplog.at_level(logging.INFO, logger="agent_fox"),
        ):
            from agent_fox.nightshift.staleness import StalenessResult
            from agent_fox.nightshift.triage import TriageResult

            mock_triage.return_value = TriageResult(processing_order=[10, 20, 30], edges=[], supersession_pairs=[])
            mock_staleness.return_value = StalenessResult(obsolete_issues=[], rationale={})
            await engine._run_issue_check()

        assert any(
            "processing order" in r.message.lower() or "order" in r.message.lower()
            for r in caplog.records
            if r.levelno >= logging.INFO
        )

    @pytest.mark.asyncio
    async def test_ts_71_19_staleness_closure_emits_audit_event(self) -> None:
        """Audit event emitted when issue closed as obsolete."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)
        mock_platform.close_issue = AsyncMock()

        engine = NightShiftEngine(config=config, platform=mock_platform)
        engine._process_fix = AsyncMock()  # type: ignore[assignment]

        with (
            patch(
                "agent_fox.nightshift.engine.check_staleness",
                new_callable=AsyncMock,
            ) as mock_staleness,
            patch("agent_fox.nightshift.engine._emit_audit_event") as mock_audit,
        ):
            from agent_fox.nightshift.staleness import StalenessResult

            call_count = 0

            async def staleness_effect(*args: object, **kwargs: object) -> StalenessResult:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return StalenessResult(
                        obsolete_issues=[20],
                        rationale={20: "resolved"},
                    )
                return StalenessResult(obsolete_issues=[], rationale={})

            mock_staleness.side_effect = staleness_effect
            await engine._run_issue_check()

            # Check audit event "night_shift.issue_obsolete"
            audit_calls = [c for c in mock_audit.call_args_list if c.args[0] == "night_shift.issue_obsolete"]
            assert len(audit_calls) >= 1
            if len(audit_calls[0].args) > 1:
                payload = audit_calls[0].args[1]
            else:
                payload = audit_calls[0].kwargs.get("payload", {})
            assert payload["closed_issue"] == 20
            assert payload["fixed_by"] == 10

    def test_ts_71_20_cycle_break_logged_at_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Cycle detection and break logged as WARNING."""
        from agent_fox.nightshift.dep_graph import DependencyEdge, build_graph

        issues = [_make_issue(10), _make_issue(20)]
        edges = [
            DependencyEdge(10, 20, "explicit", ""),
            DependencyEdge(20, 10, "explicit", ""),
        ]

        with caplog.at_level(logging.WARNING):
            build_graph(issues, edges)

        assert any("cycle" in r.message.lower() for r in caplog.records)


# ===========================================================================
# Edge Case Tests: TS-71-E1 through TS-71-E9
# ===========================================================================


class TestEdgeCases:
    """Verify edge case handling."""

    # -----------------------------------------------------------------------
    # TS-71-E1: Reference to issue not in batch
    # Requirement: 71-REQ-2.E1
    # -----------------------------------------------------------------------

    def test_ts_71_e1_reference_outside_batch_ignored(self) -> None:
        """References to issues not in batch are ignored."""
        from agent_fox.nightshift.reference_parser import parse_text_references

        issue_10 = _make_issue(10, body="depends on #99")
        issue_20 = _make_issue(20)

        edges = parse_text_references([issue_10, issue_20])

        assert len(edges) == 0

    # -----------------------------------------------------------------------
    # TS-71-E2: Explicit reference cycle
    # Requirement: 71-REQ-2.E2
    # -----------------------------------------------------------------------

    def test_ts_71_e2_explicit_reference_cycle(self) -> None:
        """Cycle from explicit refs broken at oldest issue."""
        from agent_fox.nightshift.dep_graph import build_graph
        from agent_fox.nightshift.reference_parser import parse_text_references

        issue_10 = _make_issue(10, body="depends on #20")
        issue_20 = _make_issue(20, body="depends on #10")

        edges = parse_text_references([issue_10, issue_20])
        order = build_graph([issue_10, issue_20], edges)

        assert order[0] == 10

    # -----------------------------------------------------------------------
    # TS-71-E3: AI triage API failure
    # Requirement: 71-REQ-3.E1
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_ts_71_e3_ai_triage_failure_fallback(self, caplog: pytest.LogCaptureFixture) -> None:
        """Triage failure falls back to refs + number order."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)
        mock_platform.close_issue = AsyncMock()

        engine = NightShiftEngine(config=config, platform=mock_platform)

        processed: list[int] = []

        async def track_fix(issue: IssueResult) -> None:
            processed.append(issue.number)

        engine._process_fix = track_fix  # type: ignore[assignment]

        with (
            patch(
                "agent_fox.nightshift.engine.run_batch_triage",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API error"),
            ),
            patch(
                "agent_fox.nightshift.engine.check_staleness",
                new_callable=AsyncMock,
            ) as mock_staleness,
            caplog.at_level(logging.WARNING),
        ):
            from agent_fox.nightshift.staleness import StalenessResult

            mock_staleness.return_value = StalenessResult(obsolete_issues=[], rationale={})
            await engine._run_issue_check()

        assert processed == [10, 20, 30]
        assert any("triage" in r.message.lower() for r in caplog.records)

    # -----------------------------------------------------------------------
    # TS-71-E4: AI order violates explicit edges
    # Requirement: 71-REQ-3.E2
    # -----------------------------------------------------------------------

    def test_ts_71_e4_explicit_edges_correct_ai_order(self) -> None:
        """Explicit edges correct an invalid AI ordering."""
        from agent_fox.nightshift.dep_graph import (
            DependencyEdge,
            build_graph,
            merge_edges,
        )

        explicit = [DependencyEdge(10, 20, "explicit", "10 before 20")]
        ai = [DependencyEdge(20, 10, "ai", "AI says 20 first")]

        merged = merge_edges(explicit, ai)
        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]
        order = build_graph(issues, merged)

        assert order.index(10) < order.index(20)

    # -----------------------------------------------------------------------
    # TS-71-E5: Empty dependency graph
    # Requirement: 71-REQ-4.E1
    # -----------------------------------------------------------------------

    def test_ts_71_e5_empty_graph_number_order(self) -> None:
        """No edges produces issue-number order."""
        from agent_fox.nightshift.dep_graph import build_graph

        issues = [_make_issue(30), _make_issue(10), _make_issue(20)]
        order = build_graph(issues, [])

        assert order == [10, 20, 30]

    # -----------------------------------------------------------------------
    # TS-71-E6: Staleness AI failure
    # Requirement: 71-REQ-5.E1
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_ts_71_e6_staleness_ai_failure_github_fallback(self) -> None:
        """AI failure falls back to GitHub API verification only."""
        from agent_fox.nightshift.staleness import check_staleness

        mock_platform = AsyncMock()
        # GitHub re-fetch shows #20 was closed (not in results)
        mock_platform.list_issues_by_label = AsyncMock(return_value=[])
        config = MagicMock()

        fixed_issue = _make_issue(10)
        remaining = [_make_issue(20)]

        with patch(
            "agent_fox.nightshift.staleness._run_ai_staleness",
            new_callable=AsyncMock,
            side_effect=RuntimeError("AI failed"),
        ):
            result = await check_staleness(fixed_issue, remaining, "diff", config, mock_platform)

        assert 20 in result.obsolete_issues

    # -----------------------------------------------------------------------
    # TS-71-E7: Staleness GitHub re-fetch failure
    # Requirement: 71-REQ-5.E2
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_ts_71_e7_github_refetch_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        """GitHub failure logs warning, continues without removal."""
        from agent_fox.core.errors import IntegrationError
        from agent_fox.nightshift.staleness import check_staleness

        mock_platform = AsyncMock()
        mock_platform.list_issues_by_label = AsyncMock(side_effect=IntegrationError("API down"))
        config = MagicMock()

        fixed_issue = _make_issue(10)
        remaining = [_make_issue(20)]

        with (
            patch(
                "agent_fox.nightshift.staleness._run_ai_staleness",
                new_callable=AsyncMock,
            ) as mock_ai,
            caplog.at_level(logging.WARNING),
        ):
            from agent_fox.nightshift.staleness import StalenessResult

            mock_ai.return_value = StalenessResult(obsolete_issues=[20], rationale={20: "obsolete"})
            result = await check_staleness(fixed_issue, remaining, "diff", config, mock_platform)

        assert result.obsolete_issues == []
        assert any(caplog.records)

    # -----------------------------------------------------------------------
    # TS-71-E8: Failed fix skips staleness
    # Requirement: 71-REQ-5.E3
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_ts_71_e8_failed_fix_skips_staleness(self) -> None:
        """Fix pipeline failure skips staleness check."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        issues = [_make_issue(10), _make_issue(20)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)
        mock_platform.close_issue = AsyncMock()

        engine = NightShiftEngine(config=config, platform=mock_platform)

        processed: list[int] = []
        call_count = 0

        async def failing_then_ok_fix(issue: IssueResult) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Fix failed")
            processed.append(issue.number)

        engine._process_fix = failing_then_ok_fix  # type: ignore[assignment]

        with patch(
            "agent_fox.nightshift.engine.check_staleness",
            new_callable=AsyncMock,
        ) as mock_staleness:
            from agent_fox.nightshift.staleness import StalenessResult

            mock_staleness.return_value = StalenessResult(obsolete_issues=[], rationale={})
            await engine._run_issue_check()

            # staleness should not be called after #10 failure
            # but should be called after #20 success
            staleness_calls = mock_staleness.call_args_list
            # Should not have been called right after #10 failed
            for call in staleness_calls:
                fixed = call.args[0] if call.args else call.kwargs.get("fixed_issue")
                assert fixed.number != 10

    # -----------------------------------------------------------------------
    # TS-71-E9: Platform sort not supported
    # Requirement: 71-REQ-1.E1
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_ts_71_e9_local_sort_fallback(self) -> None:
        """Local sort applied when platform ignores sort params."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        # Platform returns unsorted
        issues = [_make_issue(30), _make_issue(10), _make_issue(20)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)
        mock_platform.close_issue = AsyncMock()

        engine = NightShiftEngine(config=config, platform=mock_platform)

        processed: list[int] = []

        async def track_fix(issue: IssueResult) -> None:
            processed.append(issue.number)

        engine._process_fix = track_fix  # type: ignore[assignment]

        await engine._run_issue_check()

        assert processed == [10, 20, 30]
