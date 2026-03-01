"""Hook runner tests.

Test Spec: TS-06-1 (pre-session order), TS-06-2 (post-session context),
           TS-06-3 (abort mode), TS-06-4 (warn mode), TS-06-5 (timeout),
           TS-06-6 (env vars), TS-06-7 (sync barrier context),
           TS-06-8 (no-hooks bypass)
Edge Cases: TS-06-E1 (no hooks configured), TS-06-E2 (hook not found)
Requirements: 06-REQ-1.1, 06-REQ-1.2, 06-REQ-1.E1, 06-REQ-2.1, 06-REQ-2.2,
              06-REQ-2.3, 06-REQ-2.E1, 06-REQ-3.1, 06-REQ-3.2, 06-REQ-4.1,
              06-REQ-4.2, 06-REQ-5.1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.core.config import HookConfig
from agent_fox.core.errors import HookError
from agent_fox.hooks.runner import (
    HookContext,
    build_hook_env,
    run_hook,
    run_post_session_hooks,
    run_pre_session_hooks,
    run_sync_barrier_hooks,
)


class TestPreSessionHooksOrder:
    """TS-06-1: Pre-session hooks execute in order.

    Requirement: 06-REQ-1.1
    """

    def test_hooks_execute_in_order(
        self,
        tmp_hook_script,
        hook_context: HookContext,
        marker_file: Path,
    ) -> None:
        """Two pre-session hooks write to a marker file in order."""
        script_a = tmp_hook_script(
            f'#!/bin/sh\nprintf "a" >> "{marker_file}"\n',
            name="hook_a.sh",
        )
        script_b = tmp_hook_script(
            f'#!/bin/sh\nprintf "b" >> "{marker_file}"\n',
            name="hook_b.sh",
        )

        config = HookConfig(pre_code=[script_a, script_b])
        results = run_pre_session_hooks(hook_context, config)

        assert len(results) == 2
        assert results[0].exit_code == 0
        assert results[1].exit_code == 0
        assert marker_file.read_text() == "ab"

    def test_returns_hook_results(
        self,
        tmp_hook_script,
        hook_context: HookContext,
    ) -> None:
        """Pre-session hooks return a list of HookResult objects."""
        script = tmp_hook_script("#!/bin/sh\nexit 0\n", name="ok.sh")
        config = HookConfig(pre_code=[script])

        results = run_pre_session_hooks(hook_context, config)
        assert len(results) == 1
        assert results[0].exit_code == 0
        assert results[0].timed_out is False


class TestPostSessionHooksContext:
    """TS-06-2: Post-session hooks execute and receive correct context.

    Requirement: 06-REQ-1.2
    """

    def test_post_hooks_receive_context(
        self,
        tmp_hook_script,
        hook_context: HookContext,
        marker_file: Path,
    ) -> None:
        """Post-session hook writes AF_SPEC_NAME and AF_TASK_GROUP to marker."""
        script = tmp_hook_script(
            f'#!/bin/sh\necho "$AF_SPEC_NAME $AF_TASK_GROUP" > "{marker_file}"\n',
            name="write_context.sh",
        )

        config = HookConfig(post_code=[script])
        results = run_post_session_hooks(hook_context, config)

        assert len(results) == 1
        assert results[0].exit_code == 0
        content = marker_file.read_text()
        assert "03_session" in content
        assert "2" in content


class TestHookAbortMode:
    """TS-06-3: Hook abort mode raises HookError.

    Requirements: 06-REQ-2.1, 06-REQ-2.3
    """

    def test_abort_mode_raises_on_failure(
        self,
        tmp_hook_script,
        hook_context: HookContext,
    ) -> None:
        """A failing hook in abort mode raises HookError."""
        script = tmp_hook_script("#!/bin/sh\nexit 1\n", name="fail.sh")

        with pytest.raises(HookError):
            run_hook(script, hook_context, mode="abort")

    def test_default_mode_is_abort(
        self,
        tmp_hook_script,
        hook_context: HookContext,
    ) -> None:
        """Hooks default to abort mode when no explicit mode is set."""
        script = tmp_hook_script("#!/bin/sh\nexit 1\n", name="fail.sh")

        # mode defaults to "abort"
        with pytest.raises(HookError):
            run_hook(script, hook_context)


class TestHookWarnMode:
    """TS-06-4: Hook warn mode logs and continues.

    Requirement: 06-REQ-2.2
    """

    def test_warn_mode_does_not_raise(
        self,
        tmp_hook_script,
        hook_context: HookContext,
    ) -> None:
        """A failing hook in warn mode returns result without raising."""
        script = tmp_hook_script("#!/bin/sh\nexit 1\n", name="fail.sh")

        result = run_hook(script, hook_context, mode="warn")
        assert result.exit_code == 1
        assert result.timed_out is False

    def test_warn_mode_logs_warning(
        self,
        tmp_hook_script,
        hook_context: HookContext,
        caplog,
    ) -> None:
        """A failing hook in warn mode logs a warning."""
        script = tmp_hook_script("#!/bin/sh\nexit 1\n", name="fail.sh")

        import logging

        with caplog.at_level(logging.WARNING, logger="agent_fox.hooks.runner"):
            run_hook(script, hook_context, mode="warn")

        assert any("warn" in record.message.lower() or "fail" in record.message.lower()
                    for record in caplog.records)


class TestHookTimeout:
    """TS-06-5: Hook timeout terminates subprocess.

    Requirements: 06-REQ-3.1, 06-REQ-3.2
    """

    def test_timeout_raises_in_abort_mode(
        self,
        tmp_hook_script,
        hook_context: HookContext,
    ) -> None:
        """A hook that exceeds timeout is treated as failure in abort mode."""
        script = tmp_hook_script("#!/bin/sh\nsleep 10\n", name="slow.sh")

        with pytest.raises(HookError):
            run_hook(script, hook_context, timeout=2, mode="abort")

    def test_timeout_returns_result_in_warn_mode(
        self,
        tmp_hook_script,
        hook_context: HookContext,
    ) -> None:
        """A timed-out hook in warn mode returns result with timed_out=True."""
        script = tmp_hook_script("#!/bin/sh\nsleep 10\n", name="slow.sh")

        result = run_hook(script, hook_context, timeout=2, mode="warn")
        assert result.timed_out is True


class TestHookContextEnvVars:
    """TS-06-6: Hook context environment variables.

    Requirement: 06-REQ-4.1
    """

    def test_build_hook_env_contains_af_vars(self) -> None:
        """build_hook_env produces correct AF_* environment variables."""
        context = HookContext(
            spec_name="05_platform",
            task_group="3",
            workspace="/tmp/ws",
            branch="feature/05/3",
        )
        env = build_hook_env(context)

        assert env["AF_SPEC_NAME"] == "05_platform"
        assert env["AF_TASK_GROUP"] == "3"
        assert env["AF_WORKSPACE"] == "/tmp/ws"
        assert env["AF_BRANCH"] == "feature/05/3"

    def test_build_hook_env_inherits_os_env(self) -> None:
        """build_hook_env includes existing environment variables."""
        context = HookContext(
            spec_name="test",
            task_group="1",
            workspace="/tmp",
            branch="feature/test",
        )
        env = build_hook_env(context)

        # Should contain standard env vars like PATH
        assert "PATH" in env


class TestSyncBarrierHookContext:
    """TS-06-7: Sync barrier hook context.

    Requirement: 06-REQ-4.2
    """

    def test_sync_barrier_special_context(
        self,
        tmp_hook_script,
        marker_file: Path,
    ) -> None:
        """Sync barrier hooks receive AF_SPEC_NAME='__sync_barrier__'."""
        script = tmp_hook_script(
            f'#!/bin/sh\necho "$AF_SPEC_NAME" > "{marker_file}"\n',
            name="write_spec.sh",
        )

        config = HookConfig(sync_barrier=[script])
        results = run_sync_barrier_hooks(barrier_number=3, config=config)

        assert len(results) == 1
        assert results[0].exit_code == 0
        assert "__sync_barrier__" in marker_file.read_text()

    def test_sync_barrier_task_group_is_barrier_number(
        self,
        tmp_hook_script,
        marker_file: Path,
    ) -> None:
        """Sync barrier hooks receive AF_TASK_GROUP as the barrier number."""
        script = tmp_hook_script(
            f'#!/bin/sh\necho "$AF_TASK_GROUP" > "{marker_file}"\n',
            name="write_group.sh",
        )

        config = HookConfig(sync_barrier=[script])
        results = run_sync_barrier_hooks(barrier_number=5, config=config)

        assert len(results) == 1
        assert "5" in marker_file.read_text()


class TestNoHooksFlag:
    """TS-06-8: No-hooks flag skips all hooks.

    Requirement: 06-REQ-5.1
    """

    def test_pre_session_skipped(
        self,
        hook_context: HookContext,
    ) -> None:
        """Pre-session hooks return empty list when no_hooks=True."""
        config = HookConfig(pre_code=["some_script.sh"])
        results = run_pre_session_hooks(hook_context, config, no_hooks=True)
        assert results == []

    def test_post_session_skipped(
        self,
        hook_context: HookContext,
    ) -> None:
        """Post-session hooks return empty list when no_hooks=True."""
        config = HookConfig(post_code=["some_script.sh"])
        results = run_post_session_hooks(hook_context, config, no_hooks=True)
        assert results == []

    def test_sync_barrier_skipped(self) -> None:
        """Sync barrier hooks return empty list when no_hooks=True."""
        config = HookConfig(sync_barrier=["some_script.sh"])
        results = run_sync_barrier_hooks(1, config, no_hooks=True)
        assert results == []


# -- Edge case tests ---------------------------------------------------------


class TestNoHooksConfigured:
    """TS-06-E1: No hooks configured.

    Requirement: 06-REQ-1.E1
    """

    def test_empty_pre_hooks_returns_empty(
        self,
        hook_context: HookContext,
    ) -> None:
        """Empty pre_code list returns empty results."""
        config = HookConfig(pre_code=[])
        results = run_pre_session_hooks(hook_context, config)
        assert results == []

    def test_empty_post_hooks_returns_empty(
        self,
        hook_context: HookContext,
    ) -> None:
        """Empty post_code list returns empty results."""
        config = HookConfig(post_code=[])
        results = run_post_session_hooks(hook_context, config)
        assert results == []


class TestHookScriptNotFound:
    """TS-06-E2: Hook script not found.

    Requirement: 06-REQ-2.E1
    """

    def test_nonexistent_hook_abort_mode_raises(
        self,
        hook_context: HookContext,
    ) -> None:
        """A non-existent hook script in abort mode raises HookError."""
        config = HookConfig(pre_code=["/nonexistent/hook.sh"])

        with pytest.raises(HookError):
            run_pre_session_hooks(hook_context, config)

    def test_nonexistent_hook_warn_mode_continues(
        self,
        hook_context: HookContext,
    ) -> None:
        """A non-existent hook script in warn mode logs and continues."""
        config = HookConfig(
            pre_code=["/nonexistent/hook.sh"],
            modes={"/nonexistent/hook.sh": "warn"},
        )

        # Should not raise; returns a result with non-zero exit code
        results = run_pre_session_hooks(hook_context, config)
        assert len(results) == 1
        assert results[0].exit_code != 0
