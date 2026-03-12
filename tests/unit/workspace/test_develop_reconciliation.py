"""Unit tests for develop branch reconciliation.

Test Spec: TS-36-3, TS-36-8, TS-36-9, TS-36-E1, TS-36-E2, TS-36-E3,
           TS-36-P1, TS-36-P2
Requirements: 36-REQ-1.1 through 36-REQ-1.3, 36-REQ-1.E1, 36-REQ-2.E1,
              36-REQ-2.E2, 36-REQ-3.1, 36-REQ-3.2,
              45-REQ-5.1, 45-REQ-6.2
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent_fox.workspace.workspace import _sync_develop_with_remote

# ---- Helpers ----


def _make_diverged_mock(
    *,
    rebase_fails: bool = True,
    merge_fails: bool = True,
    ours_fails: bool = True,
    checkout_fails: bool = False,
):
    """Create a run_git mock for a diverged develop scenario.

    Controls which strategies fail to test the fallback chain.
    """
    calls: list[list[str]] = []

    async def mock_run_git(args: list[str], cwd: Path, check: bool = True):
        calls.append(list(args))
        key = " ".join(args)

        # rev-list counts: diverged (both ahead)
        if "rev-list" in key and "develop..origin/develop" in key:
            return 0, "2\n", ""
        if "rev-list" in key and "origin/develop..develop" in key:
            return 0, "3\n", ""

        # symbolic-ref for current branch
        if "symbolic-ref" in key:
            return 0, "some-branch\n", ""

        # checkout develop
        if key == "checkout develop":
            if checkout_fails:
                return 1, "", "error: checkout failed"
            return 0, "", ""

        # rebase origin/develop
        if "rebase" in key and "origin/develop" in key and "--abort" not in key:
            if rebase_fails:
                return 1, "", "CONFLICT"
            return 0, "", ""

        # rebase --abort
        if "rebase" in key and "--abort" in key:
            return 0, "", ""

        # merge with -X ours
        if "merge" in key and "-X" in key and "ours" in key:
            if ours_fails:
                return 1, "CONFLICT", ""
            return 0, "", ""

        # merge --abort
        if "merge" in key and "--abort" in key:
            return 0, "", ""

        # plain merge (no -X)
        if "merge" in key and "--no-edit" in key and "-X" not in key:
            if merge_fails:
                return 1, "CONFLICT", ""
            return 0, "", ""

        # checkout back to original branch
        if "checkout" in key and "some-branch" in key:
            return 0, "", ""

        return 0, "", ""

    return mock_run_git, calls


def _make_synced_mock(*, local_ahead: int = 0, remote_ahead: int = 0):
    """Create a run_git mock for non-diverged states."""
    calls: list[list[str]] = []

    async def mock_run_git(args: list[str], cwd: Path, check: bool = True):
        calls.append(list(args))
        key = " ".join(args)

        if "rev-list" in key and "develop..origin/develop" in key:
            return 0, f"{remote_ahead}\n", ""
        if "rev-list" in key and "origin/develop..develop" in key:
            return 0, f"{local_ahead}\n", ""

        # fast-forward path
        if "branch" in key and "-f" in key:
            return 0, "", ""

        return 0, "", ""

    return mock_run_git, calls


# ---------------------------------------------------------------------------
# TS-36-3: All Strategies Fail Falls Back to Warning
# ---------------------------------------------------------------------------


class TestAllStrategiesFailWarning:
    """TS-36-3: When all merge strategies fail, a warning is logged and
    local develop is used as-is.

    Requirement: 36-REQ-1.3
    """

    @pytest.mark.asyncio
    async def test_all_strategies_fail_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """All strategies fail -> warning logged, no exception."""
        mock_run_git, calls = _make_diverged_mock(
            rebase_fails=True, merge_fails=True, ours_fails=True
        )

        with patch("agent_fox.workspace.workspace.run_git", side_effect=mock_run_git):
            with caplog.at_level(logging.WARNING):
                await _sync_develop_with_remote(tmp_path)

        # Should warn about using local as-is
        assert any(
            "as-is" in r.message.lower() or "using local" in r.message.lower()
            for r in caplog.records
        ), (
            "Expected 'using local as-is' warning, got: "
            f"{[r.message for r in caplog.records]}"
        )

    @pytest.mark.asyncio
    async def test_all_strategies_fail_no_exception(self, tmp_path: Path) -> None:
        """All strategies fail -> no exception raised."""
        mock_run_git, _ = _make_diverged_mock(
            rebase_fails=True, merge_fails=True, ours_fails=True
        )

        with patch("agent_fox.workspace.workspace.run_git", side_effect=mock_run_git):
            # Should not raise
            await _sync_develop_with_remote(tmp_path)


# ---------------------------------------------------------------------------
# TS-36-8: In-Sync Develop Is No-Op
# ---------------------------------------------------------------------------


class TestInSyncNoOp:
    """TS-36-8: When local and origin are in sync, no git operations
    beyond the divergence check.

    Requirement: 36-REQ-3.1
    """

    @pytest.mark.asyncio
    async def test_in_sync_no_merge_or_rebase(self, tmp_path: Path) -> None:
        """No merge/rebase called when branches are in sync."""
        mock_run_git, calls = _make_synced_mock(local_ahead=0, remote_ahead=0)

        with patch("agent_fox.workspace.workspace.run_git", side_effect=mock_run_git):
            await _sync_develop_with_remote(tmp_path)

        all_cmds = [" ".join(c) for c in calls]
        assert not any("merge" in cmd for cmd in all_cmds), (
            f"merge should not be called when in sync, got: {all_cmds}"
        )
        assert not any("rebase" in cmd for cmd in all_cmds), (
            f"rebase should not be called when in sync, got: {all_cmds}"
        )


# ---------------------------------------------------------------------------
# TS-36-9: Local-Ahead Develop Unchanged
# ---------------------------------------------------------------------------


class TestLocalAheadUnchanged:
    """TS-36-9: When local has commits origin lacks but origin has no extra
    commits, local develop is not modified.

    Requirement: 36-REQ-3.2
    """

    @pytest.mark.asyncio
    async def test_local_ahead_no_modifications(self, tmp_path: Path) -> None:
        """Local ahead -> no merge/rebase/branch-force calls."""
        mock_run_git, calls = _make_synced_mock(local_ahead=2, remote_ahead=0)

        with patch("agent_fox.workspace.workspace.run_git", side_effect=mock_run_git):
            await _sync_develop_with_remote(tmp_path)

        all_cmds = [" ".join(c) for c in calls]
        assert not any("merge" in cmd for cmd in all_cmds)
        assert not any("rebase" in cmd for cmd in all_cmds)
        assert not any("branch -f" in cmd for cmd in all_cmds)


# ---------------------------------------------------------------------------
# TS-36-E1: Checkout Develop Fails
# ---------------------------------------------------------------------------


class TestCheckoutDevelopFails:
    """TS-36-E1: When checkout of develop fails, reconciliation is skipped.

    Requirement: 36-REQ-1.E1
    """

    @pytest.mark.asyncio
    async def test_checkout_fail_skips_reconciliation(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Checkout failure -> warning logged, no merge/rebase attempted."""
        mock_run_git, calls = _make_diverged_mock(checkout_fails=True)

        with patch("agent_fox.workspace.workspace.run_git", side_effect=mock_run_git):
            with caplog.at_level(logging.WARNING):
                await _sync_develop_with_remote(tmp_path)

        # Warning should mention checkout failure
        assert any(
            "checkout" in r.message.lower() or "could not" in r.message.lower()
            for r in caplog.records
        ), (
            "Expected checkout failure warning, got: "
            f"{[r.message for r in caplog.records]}"
        )

        # No merge/rebase should have been attempted
        all_cmds = [" ".join(c) for c in calls]
        assert not any("merge" in cmd and "--no-edit" in cmd for cmd in all_cmds), (
            "merge should not be attempted after checkout failure"
        )


# ---------------------------------------------------------------------------
# TS-36-E2: Fetch Fails During Post-Harvest
# ---------------------------------------------------------------------------


class TestFetchFailsPostHarvest:
    """TS-36-E2: When fetch fails during post-harvest, push is attempted as-is.

    Requirement: 36-REQ-2.E2
    """

    @pytest.mark.asyncio
    async def test_fetch_fail_still_pushes(self, tmp_path: Path) -> None:
        """Fetch failure -> push attempted without reconciliation."""
        calls: list[list[str]] = []

        async def mock_run_git(args: list[str], cwd: Path, check: bool = True):
            from agent_fox.core.errors import WorkspaceError

            calls.append(list(args))
            key = " ".join(args)

            # rev-list: origin is ahead (diverged)
            if "rev-list" in key and "develop..origin/develop" in key:
                return 0, "2\n", ""
            if "rev-list" in key and "origin/develop..develop" in key:
                return 0, "1\n", ""

            # fetch fails
            if "fetch" in key:
                if check:
                    raise WorkspaceError("fetch failed")
                return 1, "", "fetch failed"

            # push succeeds
            if "push" in key:
                return 0, "", ""

            return 0, "", ""

        with patch("agent_fox.workspace.harvest.run_git", side_effect=mock_run_git):
            with patch(
                "agent_fox.workspace.workspace.run_git",
                side_effect=mock_run_git,
            ):
                from agent_fox.workspace.harvest import _push_develop_if_pushable

                await _push_develop_if_pushable(tmp_path)

        all_cmds = [" ".join(c) for c in calls]
        assert any("push" in cmd for cmd in all_cmds), (
            f"push should be attempted even when fetch fails, got: {all_cmds}"
        )


# ---------------------------------------------------------------------------
# TS-36-E3: Push Fails After Reconciliation
# ---------------------------------------------------------------------------


class TestPushFailsAfterReconciliation:
    """TS-36-E3: When push fails even after successful reconciliation,
    a warning is logged.

    Requirement: 36-REQ-2.E1
    """

    @pytest.mark.asyncio
    async def test_push_fail_after_reconcile_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Push failure after reconciliation -> warning, no exception."""
        calls: list[list[str]] = []

        async def mock_run_git(args: list[str], cwd: Path, check: bool = True):
            calls.append(list(args))
            key = " ".join(args)

            # rev-list: origin is ahead
            if "rev-list" in key and "develop..origin/develop" in key:
                return 0, "2\n", ""
            if "rev-list" in key and "origin/develop..develop" in key:
                return 0, "1\n", ""

            # fetch succeeds
            if "fetch" in key:
                return 0, "", ""

            # For sync: symbolic-ref
            if "symbolic-ref" in key:
                return 0, "some-branch\n", ""

            # checkout
            if "checkout" in key:
                return 0, "", ""

            # rebase succeeds (reconciliation works)
            if "rebase" in key and "--abort" not in key:
                return 0, "", ""

            # push always fails
            if "push" in key:
                return 1, "", "rejected: non-fast-forward"

            return 0, "", ""

        with patch("agent_fox.workspace.harvest.run_git", side_effect=mock_run_git):
            with patch(
                "agent_fox.workspace.workspace.run_git",
                side_effect=mock_run_git,
            ):
                from agent_fox.workspace.harvest import _push_develop_if_pushable

                with caplog.at_level(logging.WARNING):
                    # Should not raise
                    await _push_develop_if_pushable(tmp_path)

        # Should warn about push failure
        assert any(
            "push" in r.message.lower() and "fail" in r.message.lower()
            for r in caplog.records
        ), f"Expected push failure warning, got: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# TS-36-P1: Fallback Chain Ordering (Property Test)
# ---------------------------------------------------------------------------


class TestFallbackChainOrdering:
    """TS-36-P1: The reconciliation function always tries strategies in order:
    rebase, merge, merge -X ours, warn.

    Property: Property 1 from design.md
    Validates: 36-REQ-1.1, 36-REQ-1.2, 36-REQ-1.3
    """

    @pytest.mark.asyncio
    async def test_rebase_only_when_rebase_succeeds(self, tmp_path: Path) -> None:
        """When rebase succeeds, no merge is attempted."""
        mock_run_git, calls = _make_diverged_mock(
            rebase_fails=False, merge_fails=False, ours_fails=False
        )

        with patch("agent_fox.workspace.workspace.run_git", side_effect=mock_run_git):
            await _sync_develop_with_remote(tmp_path)

        all_cmds = [" ".join(c) for c in calls]
        assert any("rebase" in cmd and "origin/develop" in cmd for cmd in all_cmds)
        assert not any("merge" in cmd and "--no-edit" in cmd for cmd in all_cmds)

    @pytest.mark.asyncio
    async def test_rebase_then_merge_when_rebase_fails(self, tmp_path: Path) -> None:
        """When rebase fails but merge succeeds, merge is called after rebase."""
        mock_run_git, calls = _make_diverged_mock(
            rebase_fails=True, merge_fails=False, ours_fails=False
        )

        with patch("agent_fox.workspace.workspace.run_git", side_effect=mock_run_git):
            await _sync_develop_with_remote(tmp_path)

        all_cmds = [" ".join(c) for c in calls]
        # Both rebase and merge attempted
        assert any("rebase" in cmd and "origin/develop" in cmd for cmd in all_cmds)
        assert any(
            "merge" in cmd and "--no-edit" in cmd and "-X" not in cmd
            for cmd in all_cmds
        )
        # No -X ours needed (merge succeeded)
        assert not any("-X" in cmd and "ours" in cmd for cmd in all_cmds)

    @pytest.mark.asyncio
    async def test_full_chain_when_rebase_and_merge_fail(self, tmp_path: Path) -> None:
        """When rebase and merge fail, merge agent is spawned (45-REQ-5.1).

        Previously tested -X ours fallback; now verifies agent fallback
        per 45-REQ-6.2 (removal of blind -X ours strategy).
        """
        mock_run_git, calls = _make_diverged_mock(
            rebase_fails=True, merge_fails=True, ours_fails=True
        )

        with (
            patch("agent_fox.workspace.workspace.run_git", side_effect=mock_run_git),
            patch(
                "agent_fox.workspace.workspace.run_merge_agent",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_agent,
        ):
            await _sync_develop_with_remote(tmp_path)

        all_cmds = [" ".join(c) for c in calls]
        assert any("rebase" in cmd and "origin/develop" in cmd for cmd in all_cmds)
        assert any(
            "merge" in cmd and "--no-edit" in cmd and "-X" not in cmd
            for cmd in all_cmds
        )
        # No -X ours (45-REQ-6.2); merge agent called instead (45-REQ-5.1)
        assert not any("-X" in cmd and "ours" in cmd for cmd in all_cmds)
        mock_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_fail_warns(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When all strategies and merge agent fail, warning is logged.

        Previously tested all strategies including -X ours; now verifies
        agent fallback per 45-REQ-5.E1 and 45-REQ-6.2.
        """
        mock_run_git, calls = _make_diverged_mock(
            rebase_fails=True, merge_fails=True, ours_fails=True
        )

        with (
            patch("agent_fox.workspace.workspace.run_git", side_effect=mock_run_git),
            patch(
                "agent_fox.workspace.workspace.run_merge_agent",
                new_callable=AsyncMock,
                return_value=False,
            ),
            caplog.at_level(logging.WARNING),
        ):
            await _sync_develop_with_remote(tmp_path)

        all_cmds = [" ".join(c) for c in calls]
        assert any("rebase" in cmd and "origin/develop" in cmd for cmd in all_cmds)
        assert any(
            "merge" in cmd and "--no-edit" in cmd and "-X" not in cmd
            for cmd in all_cmds
        )
        # No -X ours (45-REQ-6.2)
        assert not any("-X" in cmd and "ours" in cmd for cmd in all_cmds)


# ---------------------------------------------------------------------------
# TS-36-P2: No-Op Idempotency (Property Test)
# ---------------------------------------------------------------------------


class TestNoOpIdempotency:
    """TS-36-P2: Calling _sync_develop_with_remote when already in sync or
    ahead performs no modifications.

    Property: Property 2 from design.md
    Validates: 36-REQ-3.1, 36-REQ-3.2
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "local_ahead,remote_ahead,label",
        [
            (0, 0, "in_sync"),
            (1, 0, "local_ahead_by_1"),
            (5, 0, "local_ahead_by_5"),
        ],
    )
    async def test_no_modifications_when_not_behind(
        self,
        tmp_path: Path,
        local_ahead: int,
        remote_ahead: int,
        label: str,
    ) -> None:
        """No merge/rebase/branch-force when remote is not ahead."""
        mock_run_git, calls = _make_synced_mock(
            local_ahead=local_ahead, remote_ahead=remote_ahead
        )

        with patch("agent_fox.workspace.workspace.run_git", side_effect=mock_run_git):
            await _sync_develop_with_remote(tmp_path)

        all_cmds = [" ".join(c) for c in calls]
        assert not any("merge" in cmd for cmd in all_cmds)
        assert not any("rebase" in cmd for cmd in all_cmds)
        assert not any("branch -f" in cmd for cmd in all_cmds)
