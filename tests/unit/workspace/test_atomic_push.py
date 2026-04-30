"""Tests for atomic push with retry (Spec 121).

Test Spec: TS-121-1 through TS-121-16, TS-121-E1 through TS-121-E6,
           TS-121-P1 through TS-121-P3, TS-121-SMOKE-1, TS-121-SMOKE-2
Requirements: 121-REQ-1.1 through 121-REQ-5.E1
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from agent_fox.core.errors import IntegrationError
from agent_fox.knowledge.audit import AuditEvent, AuditEventType
from agent_fox.workspace import WorkspaceInfo
from agent_fox.workspace.harvest import harvest, post_harvest_integrate
from agent_fox.workspace.merge_lock import MergeLock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeAuditSink:
    """Collects audit events for test assertions."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def emit_audit_event(self, event: AuditEvent) -> None:
        self.events.append(event)

    def record_session_outcome(self, outcome: object) -> None:
        pass

    def record_tool_call(self, call: object) -> None:
        pass

    def record_tool_error(self, error: object) -> None:
        pass

    def close(self) -> None:
        pass


class FailingAuditSink:
    """Audit sink that raises on every emit (for TS-121-E5)."""

    def emit_audit_event(self, event: AuditEvent) -> None:
        raise RuntimeError("sink broken")

    def record_session_outcome(self, outcome: object) -> None:
        pass

    def record_tool_call(self, call: object) -> None:
        pass

    def record_tool_error(self, error: object) -> None:
        pass

    def close(self) -> None:
        pass


@pytest.fixture
def fake_workspace(tmp_path: Path) -> WorkspaceInfo:
    """Create a fake workspace for testing."""
    ws_path = tmp_path / "worktree"
    ws_path.mkdir()
    return WorkspaceInfo(
        path=ws_path,
        branch="feature/test_spec/1",
        spec_name="test_spec",
        task_group=1,
    )


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """Return a temporary directory as repo root."""
    root = tmp_path / "repo"
    root.mkdir()
    return root


def _standard_harvest_mocks() -> dict:
    """Return a dict of context managers for standard harvest mocking.

    Mocks has_new_commits, get_changed_files, checkout_branch, and run_git
    to simulate a successful squash-merge without touching real git.
    """
    return {
        "has_new_commits": patch(
            "agent_fox.workspace.harvest.has_new_commits",
            new_callable=AsyncMock,
            return_value=True,
        ),
        "get_changed_files": patch(
            "agent_fox.workspace.harvest.get_changed_files",
            new_callable=AsyncMock,
            return_value=["file.py"],
        ),
        "checkout_branch": patch(
            "agent_fox.workspace.harvest.checkout_branch",
            new_callable=AsyncMock,
        ),
        "run_git": patch(
            "agent_fox.workspace.harvest.run_git",
            new_callable=AsyncMock,
            return_value=(0, "", ""),
        ),
    }


# ---------------------------------------------------------------------------
# TS-121-1: Push executes inside merge lock
# ---------------------------------------------------------------------------


class TestPushExecutesInsideMergeLock:
    """TS-121-1: push happens while the merge lock is held.

    Requirement: 121-REQ-1.1
    """

    @pytest.mark.asyncio
    async def test_push_executes_inside_merge_lock(
        self,
        repo_root: Path,
        fake_workspace: WorkspaceInfo,
    ) -> None:
        """git push is called while the merge lock is still held."""
        lock_file = repo_root / ".agent-fox" / "merge.lock"
        lock_held_during_push = []

        async def tracking_push(*args, **kwargs):
            lock_held_during_push.append(lock_file.exists())
            return True

        mocks = _standard_harvest_mocks()
        with (
            mocks["has_new_commits"],
            mocks["get_changed_files"],
            mocks["checkout_branch"],
            mocks["run_git"],
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=tracking_push,
            ),
        ):
            result = await harvest(repo_root, fake_workspace, push=True)

        assert len(lock_held_during_push) > 0, "push_to_remote was never called"
        assert lock_held_during_push[0] is True, "Lock was not held during push"
        assert not lock_file.exists(), "Lock was not released after harvest"
        assert len(result) > 0


# ---------------------------------------------------------------------------
# TS-121-2: No concurrent merge while push in progress
# ---------------------------------------------------------------------------


class TestNoConcurrentMergeWhilePushing:
    """TS-121-2: second harvest blocks until first harvest (including push) completes.

    Requirement: 121-REQ-1.2
    """

    @pytest.mark.asyncio
    async def test_no_concurrent_merge_while_push_in_progress(
        self,
        repo_root: Path,
    ) -> None:
        """Two concurrent harvest calls serialize: merge-push-merge-push."""
        ws1 = WorkspaceInfo(
            path=repo_root / "ws1",
            branch="feature/spec1/1",
            spec_name="spec1",
            task_group=1,
        )
        ws2 = WorkspaceInfo(
            path=repo_root / "ws2",
            branch="feature/spec2/1",
            spec_name="spec2",
            task_group=1,
        )
        (ws1.path).mkdir(parents=True, exist_ok=True)
        (ws2.path).mkdir(parents=True, exist_ok=True)

        call_order: list[str] = []

        async def slow_push(*args, **kwargs):
            call_order.append("push_start")
            await asyncio.sleep(0.05)
            call_order.append("push_end")
            return True

        async def tracking_run_git(args, **kwargs):
            cmd = args[0] if args else ""
            if cmd == "merge":
                call_order.append("merge")
            return (0, "", "")

        with (
            patch(
                "agent_fox.workspace.harvest.has_new_commits",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "agent_fox.workspace.harvest.get_changed_files",
                new_callable=AsyncMock,
                return_value=["file.py"],
            ),
            patch(
                "agent_fox.workspace.harvest.checkout_branch",
                new_callable=AsyncMock,
            ),
            patch(
                "agent_fox.workspace.harvest.run_git",
                side_effect=tracking_run_git,
            ),
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=slow_push,
            ),
        ):
            await asyncio.gather(
                harvest(repo_root, ws1, push=True),
                harvest(repo_root, ws2, push=True),
            )

        # Verify strict serialization: merge-push_start-push_end-merge-push_start-push_end
        assert call_order == [
            "merge", "push_start", "push_end",
            "merge", "push_start", "push_end",
        ]


# ---------------------------------------------------------------------------
# TS-121-3: Lock released after successful push
# ---------------------------------------------------------------------------


class TestLockReleasedAfterSuccessfulPush:
    """TS-121-3: lock is released and touched files returned after push.

    Requirement: 121-REQ-1.3
    """

    @pytest.mark.asyncio
    async def test_lock_released_after_successful_push(
        self,
        repo_root: Path,
        fake_workspace: WorkspaceInfo,
    ) -> None:
        """After a successful push, the lock file is removed and files returned."""
        lock_file = repo_root / ".agent-fox" / "merge.lock"

        mocks = _standard_harvest_mocks()
        with (
            mocks["has_new_commits"],
            mocks["get_changed_files"],
            mocks["checkout_branch"],
            mocks["run_git"],
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = await harvest(repo_root, fake_workspace, push=True)

        assert len(result) > 0
        assert not lock_file.exists()


# ---------------------------------------------------------------------------
# TS-121-4: Push failure triggers retry
# ---------------------------------------------------------------------------


class TestPushFailureTriggersRetry:
    """TS-121-4: push failure inside the lock invokes the retry loop.

    Requirement: 121-REQ-1.4
    """

    @pytest.mark.asyncio
    async def test_push_failure_triggers_retry(
        self,
        repo_root: Path,
        fake_workspace: WorkspaceInfo,
    ) -> None:
        """When first push fails, retry logic is invoked before lock release."""
        push_count = 0

        async def mock_push(*args, **kwargs):
            nonlocal push_count
            push_count += 1
            return push_count >= 2  # fail first, succeed second

        mocks = _standard_harvest_mocks()
        with (
            mocks["has_new_commits"],
            mocks["get_changed_files"],
            mocks["checkout_branch"],
            mocks["run_git"],
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=True,
                create=True,
            ) as mock_fetch,
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                new_callable=AsyncMock,
                create=True,
            ) as mock_rebase,
        ):
            result = await harvest(repo_root, fake_workspace, push=True)

        assert push_count == 2
        mock_fetch.assert_called_once()
        mock_rebase.assert_called_once()
        assert len(result) > 0


# ---------------------------------------------------------------------------
# TS-121-5: Retry fetches and rebases before each push attempt
# ---------------------------------------------------------------------------


class TestRetryFetchesAndRebasesBeforePush:
    """TS-121-5: fetch-rebase-push sequence on retry.

    Requirement: 121-REQ-2.1
    """

    @pytest.mark.asyncio
    async def test_retry_fetches_and_rebases_before_push(
        self,
        repo_root: Path,
    ) -> None:
        """Call order is: push, fetch, rebase, push."""
        from agent_fox.workspace.harvest import _push_with_retry

        calls: list[str] = []

        async def mock_push(*args, **kwargs):
            calls.append("push")
            return len(calls) > 2  # fail first push, succeed second

        async def mock_fetch(*args, **kwargs):
            calls.append("fetch")
            return True

        async def mock_rebase(*args, **kwargs):
            calls.append("rebase")

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                side_effect=mock_fetch,
                create=True,
            ),
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                side_effect=mock_rebase,
            ),
        ):
            await _push_with_retry(repo_root, "develop")

        assert calls == ["push", "fetch", "rebase", "push"]


# ---------------------------------------------------------------------------
# TS-121-6: Maximum 4 total push attempts
# ---------------------------------------------------------------------------


class TestMaximum4TotalPushAttempts:
    """TS-121-6: retry count bounded at 3 retries (4 total).

    Requirement: 121-REQ-2.2
    """

    @pytest.mark.asyncio
    async def test_maximum_4_total_push_attempts(
        self,
        repo_root: Path,
    ) -> None:
        """push_to_remote is called exactly 4 times when push always fails."""
        from agent_fox.workspace.harvest import _push_with_retry

        push_count = 0

        async def mock_push(*args, **kwargs):
            nonlocal push_count
            push_count += 1
            return False

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=True,
                create=True,
            ),
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                new_callable=AsyncMock,
                create=True,
            ),
        ):
            result = await _push_with_retry(repo_root, "develop", max_retries=3)

        assert result is False
        assert push_count == 4


# ---------------------------------------------------------------------------
# TS-121-7: Successful retry logs at INFO
# ---------------------------------------------------------------------------


class TestSuccessfulRetryLogsInfo:
    """TS-121-7: INFO log on successful retry.

    Requirement: 121-REQ-2.3
    """

    @pytest.mark.asyncio
    async def test_successful_retry_logs_info(
        self,
        repo_root: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """INFO log contains 'attempt 2' on successful retry."""
        from agent_fox.workspace.harvest import _push_with_retry

        call_count = 0

        async def mock_push(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=True,
                create=True,
            ),
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                new_callable=AsyncMock,
                create=True,
            ),
            caplog.at_level(logging.INFO, logger="agent_fox.workspace.harvest"),
        ):
            result = await _push_with_retry(repo_root, "develop")

        assert result is True
        assert any(
            "attempt 2" in r.message.lower()
            for r in caplog.records
            if r.levelname == "INFO"
        ), f"Expected INFO log with 'attempt 2'; got: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# TS-121-8: Exhausted retries logs WARNING
# ---------------------------------------------------------------------------


class TestExhaustedRetriesLogsWarning:
    """TS-121-8: WARNING log when all retries exhausted.

    Requirement: 121-REQ-2.4
    """

    @pytest.mark.asyncio
    async def test_exhausted_retries_logs_warning(
        self,
        repo_root: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """WARNING log on retries exhausted; function returns False."""
        from agent_fox.workspace.harvest import _push_with_retry

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=True,
                create=True,
            ),
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                new_callable=AsyncMock,
                create=True,
            ),
            caplog.at_level(logging.WARNING, logger="agent_fox.workspace.harvest"),
        ):
            result = await _push_with_retry(repo_root, "develop", max_retries=3)

        assert result is False
        assert any(
            "exhausted" in r.message.lower() or "retries" in r.message.lower()
            for r in caplog.records
            if r.levelname == "WARNING"
        ), f"Expected WARNING about retries; got: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# TS-121-9: Retries happen under merge lock
# ---------------------------------------------------------------------------


class TestRetriesHappenUnderMergeLock:
    """TS-121-9: lock is held during all retry attempts.

    Requirement: 121-REQ-2.5
    """

    @pytest.mark.asyncio
    async def test_retries_happen_under_merge_lock(
        self,
        repo_root: Path,
        fake_workspace: WorkspaceInfo,
    ) -> None:
        """Lock file exists during both push attempts."""
        lock_file = repo_root / ".agent-fox" / "merge.lock"
        lock_states: list[bool] = []

        async def tracking_push(*args, **kwargs):
            lock_states.append(lock_file.exists())
            return len(lock_states) >= 2  # fail first, succeed second

        mocks = _standard_harvest_mocks()
        with (
            mocks["has_new_commits"],
            mocks["get_changed_files"],
            mocks["checkout_branch"],
            mocks["run_git"],
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=tracking_push,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=True,
                create=True,
            ),
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                new_callable=AsyncMock,
                create=True,
            ),
        ):
            await harvest(repo_root, fake_workspace, push=True)

        assert lock_states == [True, True]


# ---------------------------------------------------------------------------
# TS-121-10: Push failure emits audit event
# ---------------------------------------------------------------------------


class TestPushFailureEmitsAuditEvent:
    """TS-121-10: audit event emitted on push failure.

    Requirement: 121-REQ-3.1
    """

    @pytest.mark.asyncio
    async def test_push_failure_emits_audit_event(
        self,
        repo_root: Path,
    ) -> None:
        """At least one git.push_failed audit event emitted on push failure."""
        from agent_fox.workspace.harvest import _push_with_retry

        sink = FakeAuditSink()
        call_count = 0

        async def mock_push(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=True,
                create=True,
            ),
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                new_callable=AsyncMock,
                create=True,
            ),
        ):
            await _push_with_retry(
                repo_root,
                "develop",
                audit_sink=sink,
                run_id="test-run",
            )

        failed_events = [
            e for e in sink.events
            if e.event_type == AuditEventType.GIT_PUSH_FAILED
        ]
        assert len(failed_events) >= 1


# ---------------------------------------------------------------------------
# TS-121-11: Audit payload includes required fields
# ---------------------------------------------------------------------------


class TestAuditPayloadIncludesRequiredFields:
    """TS-121-11: push failure audit event payload has required fields.

    Requirement: 121-REQ-3.2
    """

    @pytest.mark.asyncio
    async def test_audit_payload_includes_required_fields(
        self,
        repo_root: Path,
    ) -> None:
        """Payload contains: attempt, error, branch, will_retry."""
        from agent_fox.workspace.harvest import _push_with_retry

        sink = FakeAuditSink()
        call_count = 0

        async def mock_push(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=True,
                create=True,
            ),
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                new_callable=AsyncMock,
                create=True,
            ),
        ):
            await _push_with_retry(
                repo_root,
                "develop",
                audit_sink=sink,
                run_id="test-run",
            )

        failed_events = [
            e for e in sink.events
            if e.event_type == AuditEventType.GIT_PUSH_FAILED
        ]
        assert len(failed_events) >= 1
        payload = failed_events[0].payload
        assert "attempt" in payload
        assert "error" in payload
        assert "branch" in payload
        assert "will_retry" in payload
        assert payload["attempt"] == 1
        assert payload["will_retry"] is True


# ---------------------------------------------------------------------------
# TS-121-12: Retries exhausted emits final audit event
# ---------------------------------------------------------------------------


class TestRetriesExhaustedEmitsFinalAudit:
    """TS-121-12: final audit event has retries_exhausted: true.

    Requirement: 121-REQ-3.3
    """

    @pytest.mark.asyncio
    async def test_retries_exhausted_emits_final_audit(
        self,
        repo_root: Path,
    ) -> None:
        """Last audit event has retries_exhausted=True."""
        from agent_fox.workspace.harvest import _push_with_retry

        sink = FakeAuditSink()

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=True,
                create=True,
            ),
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                new_callable=AsyncMock,
                create=True,
            ),
        ):
            await _push_with_retry(
                repo_root,
                "develop",
                max_retries=3,
                audit_sink=sink,
                run_id="test-run",
            )

        failed_events = [
            e for e in sink.events
            if e.event_type == AuditEventType.GIT_PUSH_FAILED
        ]
        assert len(failed_events) >= 1
        last_event = failed_events[-1]
        assert last_event.payload["retries_exhausted"] is True


# ---------------------------------------------------------------------------
# TS-121-13: Successful retry emits push_retry_success
# ---------------------------------------------------------------------------


class TestSuccessfulRetryEmitsPushRetrySuccess:
    """TS-121-13: git.push_retry_success event on successful retry.

    Requirement: 121-REQ-3.4
    """

    @pytest.mark.asyncio
    async def test_successful_retry_emits_push_retry_success(
        self,
        repo_root: Path,
    ) -> None:
        """One git.push_retry_success event with total_attempts=2."""
        from agent_fox.workspace.harvest import _push_with_retry

        sink = FakeAuditSink()
        call_count = 0

        async def mock_push(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=True,
                create=True,
            ),
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                new_callable=AsyncMock,
                create=True,
            ),
        ):
            await _push_with_retry(
                repo_root,
                "develop",
                audit_sink=sink,
                run_id="test-run",
            )

        success_events = [
            e for e in sink.events
            if e.event_type == AuditEventType.GIT_PUSH_RETRY_SUCCESS
        ]
        assert len(success_events) == 1
        assert success_events[0].payload["total_attempts"] == 2


# ---------------------------------------------------------------------------
# TS-121-14: Sync under already-held lock does not deadlock
# ---------------------------------------------------------------------------


class TestSyncUnderHeldLockNoDeadlock:
    """TS-121-14: reconciliation logic runs under already-held lock.

    Requirement: 121-REQ-4.1
    """

    @pytest.mark.asyncio
    async def test_sync_under_held_lock_no_deadlock(
        self,
        repo_root: Path,
    ) -> None:
        """_sync_develop_with_remote(_lock_held=True) completes without deadlock."""
        from agent_fox.workspace.develop import _sync_develop_with_remote

        lock = MergeLock(repo_root)

        # Mock run_git to simulate remote ahead
        async def mock_run_git(args, cwd, check=True, **kwargs):
            key = " ".join(args)
            if "rev-list" in key and "develop..origin/develop" in key:
                return (0, "1\n", "")
            if "rev-list" in key and "origin/develop..develop" in key:
                return (0, "0\n", "")
            return (0, "", "")

        with patch(
            "agent_fox.workspace.develop.run_git",
            side_effect=mock_run_git,
        ):
            async with lock:
                # If this completes, no deadlock occurred
                result = await _sync_develop_with_remote(repo_root, _lock_held=True)
                assert result in (None, "fast-forward", "rebase", "merge", "merge-agent")


# ---------------------------------------------------------------------------
# TS-121-15: harvest(push=True) pushes, post_harvest_integrate skips
# ---------------------------------------------------------------------------


class TestHarvestPushTrueThenPostHarvestSkips:
    """TS-121-15: push_to_remote called exactly once across both functions.

    Requirements: 121-REQ-5.1, 121-REQ-5.3
    """

    @pytest.mark.asyncio
    async def test_harvest_push_true_then_post_harvest_skips(
        self,
        repo_root: Path,
        fake_workspace: WorkspaceInfo,
    ) -> None:
        """push_to_remote called once inside harvest, not in post_harvest."""
        push_count = 0

        async def counting_push(*args, **kwargs):
            nonlocal push_count
            push_count += 1
            return True

        mocks = _standard_harvest_mocks()
        with (
            mocks["has_new_commits"],
            mocks["get_changed_files"],
            mocks["checkout_branch"],
            mocks["run_git"],
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=counting_push,
            ),
            patch(
                "agent_fox.workspace.harvest._push_develop_if_pushable",
                new_callable=AsyncMock,
            ) as mock_push_dev,
        ):
            await harvest(repo_root, fake_workspace, push=True)
            await post_harvest_integrate(
                repo_root,
                fake_workspace,
                push_already_done=True,
            )

        assert push_count == 1
        # _push_develop_if_pushable should not be called when push_already_done=True
        mock_push_dev.assert_not_called()


# ---------------------------------------------------------------------------
# TS-121-16: harvest(push=False) skips push
# ---------------------------------------------------------------------------


class TestHarvestPushFalseSkipsPush:
    """TS-121-16: push is skipped when push=False.

    Requirement: 121-REQ-5.2
    """

    @pytest.mark.asyncio
    async def test_harvest_push_false_skips_push(
        self,
        repo_root: Path,
        fake_workspace: WorkspaceInfo,
    ) -> None:
        """push_to_remote is not called when push=False."""

        async def should_not_push(*args, **kwargs):
            raise AssertionError("push_to_remote should not be called")

        mocks = _standard_harvest_mocks()
        with (
            mocks["has_new_commits"],
            mocks["get_changed_files"],
            mocks["checkout_branch"],
            mocks["run_git"],
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=should_not_push,
            ),
        ):
            result = await harvest(repo_root, fake_workspace, push=False)

        assert len(result) > 0


# ===========================================================================
# Edge Case Tests
# ===========================================================================


# ---------------------------------------------------------------------------
# TS-121-E1: No remote configured skips push
# ---------------------------------------------------------------------------


class TestNoRemoteConfiguredSkipsPush:
    """TS-121-E1: push skipped when no remote exists.

    Requirement: 121-REQ-1.E1
    """

    @pytest.mark.asyncio
    async def test_no_remote_configured_skips_push(
        self,
        repo_root: Path,
        fake_workspace: WorkspaceInfo,
    ) -> None:
        """Harvest succeeds without pushing when no remote is configured."""

        async def should_not_push(*args, **kwargs):
            raise AssertionError("push_to_remote should not be called")

        mocks = _standard_harvest_mocks()
        with (
            mocks["has_new_commits"],
            mocks["get_changed_files"],
            mocks["checkout_branch"],
            mocks["run_git"],
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=should_not_push,
            ),
            patch(
                "agent_fox.workspace.git.get_remote_url",
                new_callable=AsyncMock,
                return_value=None,
                create=True,
            ),
        ):
            result = await harvest(repo_root, fake_workspace, push=True)

        assert len(result) > 0


# ---------------------------------------------------------------------------
# TS-121-E2: Fetch fails during retry
# ---------------------------------------------------------------------------


class TestFetchFailsDuringRetry:
    """TS-121-E2: push retried even if fetch fails.

    Requirement: 121-REQ-2.E1
    """

    @pytest.mark.asyncio
    async def test_fetch_fails_during_retry(
        self,
        repo_root: Path,
    ) -> None:
        """Rebase skipped when fetch fails; push still retried."""
        from agent_fox.workspace.harvest import _push_with_retry

        push_count = 0

        async def mock_push(*args, **kwargs):
            nonlocal push_count
            push_count += 1
            return push_count >= 3  # succeed on third attempt

        async def mock_rebase(*args, **kwargs):
            raise AssertionError("rebase should not be called after fetch failure")

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=False,
                create=True,
            ),
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                side_effect=mock_rebase,
            ),
        ):
            result = await _push_with_retry(repo_root, "develop")

        assert push_count >= 2


# ---------------------------------------------------------------------------
# TS-121-E3: Rebase conflict aborts retry
# ---------------------------------------------------------------------------


class TestRebaseConflictAbortsRetry:
    """TS-121-E3: rebase conflict stops the retry loop.

    Requirement: 121-REQ-2.E2
    """

    @pytest.mark.asyncio
    async def test_rebase_conflict_aborts_retry(
        self,
        repo_root: Path,
    ) -> None:
        """rebase_abort called, no further push after rebase failure."""
        from agent_fox.workspace.harvest import _push_with_retry

        push_count = 0

        async def mock_push(*args, **kwargs):
            nonlocal push_count
            push_count += 1
            return False

        async def mock_rebase(*args, **kwargs):
            raise IntegrationError(
                "Rebase conflict",
                branch="develop",
            )

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=True,
                create=True,
            ),
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                side_effect=mock_rebase,
            ),
            patch(
                "agent_fox.workspace.harvest.abort_rebase",
                new_callable=AsyncMock,
            ) as mock_abort,
        ):
            result = await _push_with_retry(repo_root, "develop")

        assert result is False
        assert push_count == 1, "No retry after rebase conflict"
        mock_abort.assert_called()


# ---------------------------------------------------------------------------
# TS-121-E4: Non-retryable push error stops immediately
# ---------------------------------------------------------------------------


class TestNonRetryablePushErrorStopsImmediately:
    """TS-121-E4: authentication/network errors are not retried.

    Requirement: 121-REQ-2.E3
    """

    @pytest.mark.asyncio
    async def test_non_retryable_push_error_stops_immediately(
        self,
        repo_root: Path,
    ) -> None:
        """Push attempted once, no fetch or rebase, returns False."""
        from agent_fox.workspace.harvest import _push_with_retry

        push_count = 0

        # Simulate an auth error: run_git returns rc=128 with auth error stderr.
        # _push_with_retry needs to classify this as non-retryable.
        async def mock_run_git(args, **kwargs):
            nonlocal push_count
            if isinstance(args, list) and args and args[0] == "push":
                push_count += 1
                return (128, "", "fatal: Authentication failed")
            return (0, "", "")

        with (
            patch(
                "agent_fox.workspace.harvest.run_git",
                side_effect=mock_run_git,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=True,
                create=True,
            ) as mock_fetch,
        ):
            result = await _push_with_retry(repo_root, "develop")

        assert result is False
        assert push_count == 1
        mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# TS-121-E5: Audit sink unavailable
# ---------------------------------------------------------------------------


class TestAuditSinkUnavailable:
    """TS-121-E5: push continues when audit sink raises.

    Requirement: 121-REQ-3.E1
    """

    @pytest.mark.asyncio
    async def test_audit_sink_unavailable(
        self,
        repo_root: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Function completes and push retries succeed despite broken sink."""
        from agent_fox.workspace.harvest import _push_with_retry

        failing_sink = FailingAuditSink()
        call_count = 0

        async def mock_push(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=True,
                create=True,
            ),
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                new_callable=AsyncMock,
                create=True,
            ),
            caplog.at_level(logging.WARNING, logger="agent_fox.workspace.harvest"),
        ):
            result = await _push_with_retry(
                repo_root,
                "develop",
                audit_sink=failing_sink,
                run_id="test-run",
            )

        assert result is True


# ---------------------------------------------------------------------------
# TS-121-E6: External caller of sync acquires lock
# ---------------------------------------------------------------------------


class TestExternalCallerSyncAcquiresLock:
    """TS-121-E6: _sync_develop_with_remote acquires lock by default.

    Requirement: 121-REQ-4.E1
    """

    @pytest.mark.asyncio
    async def test_external_caller_sync_acquires_lock(
        self,
        repo_root: Path,
    ) -> None:
        """Lock file is created and released during the call."""
        from agent_fox.workspace.develop import _sync_develop_with_remote

        lock_file = repo_root / ".agent-fox" / "merge.lock"
        lock_observed = False

        async def tracking_run_git(args, cwd, check=True, **kwargs):
            nonlocal lock_observed
            key = " ".join(args)
            if "rev-list" in key and "develop..origin/develop" in key:
                return (0, "1\n", "")
            if "rev-list" in key and "origin/develop..develop" in key:
                return (0, "0\n", "")
            # During actual sync operations, check if lock is held
            if "branch" in key or "merge" in key:
                lock_observed = lock_file.exists()
            return (0, "", "")

        with patch(
            "agent_fox.workspace.develop.run_git",
            side_effect=tracking_run_git,
        ):
            # Explicitly pass _lock_held=False to verify the new parameter
            # preserves existing lock-acquisition behavior.
            await _sync_develop_with_remote(repo_root, _lock_held=False)

        assert lock_observed is True, "Lock was not held during sync"
        assert not lock_file.exists(), "Lock was not released"


# ===========================================================================
# Property Tests
# ===========================================================================


# ---------------------------------------------------------------------------
# TS-121-P1: Bounded retry count
# ---------------------------------------------------------------------------


class TestPropertyBoundedRetryCount:
    """TS-121-P1: total push attempts never exceeds max_retries + 1.

    Property: Property 2 from design.md
    Validates: 121-REQ-2.2, 121-REQ-2.4
    """

    @pytest.mark.property
    @given(
        max_retries=st.integers(min_value=0, max_value=10),
        outcomes=st.lists(st.booleans(), min_size=1, max_size=15),
    )
    @settings(max_examples=50, deadline=5000)
    def test_property_bounded_retry_count(
        self,
        max_retries: int,
        outcomes: list[bool],
        tmp_path: Path,
    ) -> None:
        """Push attempts bounded by max_retries + 1 for any outcome sequence."""
        from agent_fox.workspace.harvest import _push_with_retry

        # Ensure outcomes list is long enough
        assume(len(outcomes) >= max_retries + 1)

        call_count = 0

        async def mock_push(*args, **kwargs):
            nonlocal call_count
            idx = call_count
            call_count += 1
            if idx < len(outcomes):
                return outcomes[idx]
            return True  # default to success if we run out

        async def run_test():
            with (
                patch(
                    "agent_fox.workspace.harvest.push_to_remote",
                    side_effect=mock_push,
                ),
                patch(
                    "agent_fox.workspace.harvest.fetch_remote",
                    new_callable=AsyncMock,
                    return_value=True,
                    create=True,
                ),
                patch(
                    "agent_fox.workspace.harvest.rebase_onto",
                    new_callable=AsyncMock,
                    create=True,
                ),
            ):
                await _push_with_retry(
                    tmp_path,
                    "develop",
                    max_retries=max_retries,
                )

        asyncio.get_event_loop().run_until_complete(run_test())
        assert call_count <= max_retries + 1


# ---------------------------------------------------------------------------
# TS-121-P2: Audit event completeness
# ---------------------------------------------------------------------------


class TestPropertyAuditEventCompleteness:
    """TS-121-P2: push failures always produce audit events.

    Property: Property 4 from design.md
    Validates: 121-REQ-3.1, 121-REQ-3.4
    """

    @pytest.mark.property
    @given(
        outcomes=st.lists(st.booleans(), min_size=1, max_size=5),
    )
    @settings(max_examples=50, deadline=5000)
    def test_property_audit_event_completeness(
        self,
        outcomes: list[bool],
        tmp_path: Path,
    ) -> None:
        """At least one failure event when first push fails; exactly one
        retry_success event when eventually successful."""
        from agent_fox.workspace.harvest import _push_with_retry

        # Require at least one failure to test audit events
        assume(outcomes[0] is False)

        sink = FakeAuditSink()
        call_count = 0

        async def mock_push(*args, **kwargs):
            nonlocal call_count
            idx = call_count
            call_count += 1
            if idx < len(outcomes):
                return outcomes[idx]
            return False

        async def run_test():
            with (
                patch(
                    "agent_fox.workspace.harvest.push_to_remote",
                    side_effect=mock_push,
                ),
                patch(
                    "agent_fox.workspace.harvest.fetch_remote",
                    new_callable=AsyncMock,
                    return_value=True,
                    create=True,
                ),
                patch(
                    "agent_fox.workspace.harvest.rebase_onto",
                    new_callable=AsyncMock,
                    create=True,
                ),
            ):
                await _push_with_retry(
                    tmp_path,
                    "develop",
                    max_retries=len(outcomes) - 1,
                    audit_sink=sink,
                    run_id="test-run",
                )

        asyncio.get_event_loop().run_until_complete(run_test())

        failed_events = [
            e for e in sink.events
            if e.event_type == AuditEventType.GIT_PUSH_FAILED
        ]
        success_events = [
            e for e in sink.events
            if e.event_type == AuditEventType.GIT_PUSH_RETRY_SUCCESS
        ]

        assert len(failed_events) >= 1, "Expected at least one push_failed event"

        # If eventually succeeded after initial failure, expect retry_success
        if any(outcomes[1:]):
            assert len(success_events) == 1, "Expected exactly one retry_success event"


# ---------------------------------------------------------------------------
# TS-121-P3: No double push
# ---------------------------------------------------------------------------


class TestPropertyNoDoublePush:
    """TS-121-P3: total pushes across harvest + post_harvest is at most 1.

    Property: Property 5 from design.md
    Validates: 121-REQ-5.3, 121-REQ-5.E1
    """

    @pytest.mark.property
    @given(push_flag=st.booleans())
    @settings(max_examples=10, deadline=5000)
    def test_property_no_double_push(
        self,
        push_flag: bool,
        tmp_path: Path,
    ) -> None:
        """push_to_remote called at most once across harvest + post_harvest."""
        push_count = 0

        async def counting_push(*args, **kwargs):
            nonlocal push_count
            push_count += 1
            return True

        repo_root = tmp_path / "repo"
        repo_root.mkdir(exist_ok=True)
        ws = WorkspaceInfo(
            path=tmp_path / "ws",
            branch="feature/test_spec/1",
            spec_name="test_spec",
            task_group=1,
        )
        (ws.path).mkdir(parents=True, exist_ok=True)

        async def run_test():
            mocks = _standard_harvest_mocks()
            with (
                mocks["has_new_commits"],
                mocks["get_changed_files"],
                mocks["checkout_branch"],
                mocks["run_git"],
                patch(
                    "agent_fox.workspace.harvest.push_to_remote",
                    side_effect=counting_push,
                ),
                patch(
                    "agent_fox.workspace.harvest._push_develop_if_pushable",
                    new_callable=AsyncMock,
                ),
            ):
                await harvest(repo_root, ws, push=push_flag)
                await post_harvest_integrate(
                    repo_root,
                    ws,
                    push_already_done=push_flag,
                )

        asyncio.get_event_loop().run_until_complete(run_test())
        assert push_count <= 1


# ===========================================================================
# Integration Smoke Tests
# ===========================================================================


# ---------------------------------------------------------------------------
# TS-121-SMOKE-1: End-to-end harvest with push retry
# ---------------------------------------------------------------------------


class TestSmokeHarvestPushRetry:
    """TS-121-SMOKE-1: full harvest-merge-push-retry-push flow.

    Execution Path: Path 2 from design.md
    """

    @pytest.mark.asyncio
    async def test_smoke_harvest_push_retry(
        self,
        repo_root: Path,
        fake_workspace: WorkspaceInfo,
    ) -> None:
        """End-to-end harvest with one push failure and successful retry."""
        sink = FakeAuditSink()
        git_calls: list[str] = []
        push_attempts = 0

        async def tracking_push(*args, **kwargs):
            nonlocal push_attempts
            push_attempts += 1
            git_calls.append("push")
            return push_attempts >= 2  # fail first, succeed second

        async def tracking_fetch(*args, **kwargs):
            git_calls.append("fetch")
            return True

        async def tracking_rebase(*args, **kwargs):
            git_calls.append("rebase")

        mocks = _standard_harvest_mocks()
        with (
            mocks["has_new_commits"],
            mocks["get_changed_files"],
            mocks["checkout_branch"],
            mocks["run_git"],
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=tracking_push,
            ),
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                side_effect=tracking_fetch,
                create=True,
            ),
            patch(
                "agent_fox.workspace.harvest.rebase_onto",
                side_effect=tracking_rebase,
            ),
        ):
            result = await harvest(
                repo_root,
                fake_workspace,
                push=True,
                audit_sink=sink,
                run_id="test-run",
            )

        assert len(result) > 0
        assert git_calls.count("push") == 2
        assert git_calls.count("fetch") == 1
        assert git_calls.count("rebase") == 1

        failed_events = [
            e for e in sink.events
            if e.event_type == AuditEventType.GIT_PUSH_FAILED
        ]
        success_events = [
            e for e in sink.events
            if e.event_type == AuditEventType.GIT_PUSH_RETRY_SUCCESS
        ]
        assert len(failed_events) == 1
        assert len(success_events) == 1


# ---------------------------------------------------------------------------
# TS-121-SMOKE-2: End-to-end harvest with push success first try
# ---------------------------------------------------------------------------


class TestSmokeHarvestPushSuccessFirstTry:
    """TS-121-SMOKE-2: happy path where push succeeds on first attempt.

    Execution Path: Path 1 from design.md
    """

    @pytest.mark.asyncio
    async def test_smoke_harvest_push_success_first_try(
        self,
        repo_root: Path,
        fake_workspace: WorkspaceInfo,
    ) -> None:
        """Push succeeds first try: no retries, no failure audit events."""
        sink = FakeAuditSink()

        mocks = _standard_harvest_mocks()
        with (
            mocks["has_new_commits"],
            mocks["get_changed_files"],
            mocks["checkout_branch"],
            mocks["run_git"],
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_push,
            patch(
                "agent_fox.workspace.harvest.fetch_remote",
                new_callable=AsyncMock,
                return_value=True,
                create=True,
            ) as mock_fetch,
        ):
            result = await harvest(
                repo_root,
                fake_workspace,
                push=True,
                audit_sink=sink,
                run_id="test-run",
            )

        assert len(result) > 0
        mock_push.assert_called_once()
        mock_fetch.assert_not_called()

        failed_events = [
            e for e in sink.events
            if e.event_type == AuditEventType.GIT_PUSH_FAILED
        ]
        assert len(failed_events) == 0
