"""Property tests for hook runner.

Test Spec: TS-06-P3 (hook mode determinism)
Property: Property 4 from design.md
Requirements: 06-REQ-2.1, 06-REQ-2.2, 06-REQ-2.3
"""

from __future__ import annotations

import os
import stat

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.errors import HookError
from agent_fox.hooks.runner import HookContext, run_hook


@pytest.fixture
def failing_script(tmp_path_factory) -> str:
    """Create a persistent failing script for property tests.

    Uses tmp_path_factory instead of tmp_path because Hypothesis
    examples need fresh directories.
    """
    base = tmp_path_factory.mktemp("hooks")
    script_path = base / "fail.sh"
    script_path.write_text("#!/bin/sh\nexit 1\n")
    st_result = os.stat(script_path)
    os.chmod(script_path, st_result.st_mode | stat.S_IEXEC)
    return str(script_path)


class TestHookModeDeterminism:
    """TS-06-P3: Hook mode determinism.

    Property 4: Abort mode always raises on failure; warn mode never raises.
    For any hook script with non-zero exit code, run_hook raises HookError
    if and only if mode == "abort".
    """

    @given(exit_code=st.integers(min_value=1, max_value=127))
    @settings(max_examples=20, deadline=None)
    def test_abort_mode_always_raises(
        self,
        exit_code: int,
        tmp_path_factory,
    ) -> None:
        """Abort mode always raises HookError for non-zero exit codes."""
        base = tmp_path_factory.mktemp("abort")
        script_path = base / "fail.sh"
        script_path.write_text(f"#!/bin/sh\nexit {exit_code}\n")
        st_result = os.stat(script_path)
        os.chmod(script_path, st_result.st_mode | stat.S_IEXEC)

        context = HookContext(
            spec_name="test",
            task_group="1",
            workspace=str(base),
            branch="feature/test",
        )

        with pytest.raises(HookError):
            run_hook(str(script_path), context, mode="abort")

    @given(exit_code=st.integers(min_value=1, max_value=127))
    @settings(max_examples=20, deadline=None)
    def test_warn_mode_never_raises(
        self,
        exit_code: int,
        tmp_path_factory,
    ) -> None:
        """Warn mode never raises for non-zero exit codes."""
        base = tmp_path_factory.mktemp("warn")
        script_path = base / "fail.sh"
        script_path.write_text(f"#!/bin/sh\nexit {exit_code}\n")
        st_result = os.stat(script_path)
        os.chmod(script_path, st_result.st_mode | stat.S_IEXEC)

        context = HookContext(
            spec_name="test",
            task_group="1",
            workspace=str(base),
            branch="feature/test",
        )

        # Should not raise
        result = run_hook(str(script_path), context, mode="warn")
        assert result.exit_code == exit_code

    def test_success_never_raises_either_mode(
        self,
        tmp_path_factory,
    ) -> None:
        """A successful hook (exit 0) never raises in either mode."""
        for mode in ("abort", "warn"):
            base = tmp_path_factory.mktemp(f"success_{mode}")
            script_path = base / "ok.sh"
            script_path.write_text("#!/bin/sh\nexit 0\n")
            st_result = os.stat(script_path)
            os.chmod(script_path, st_result.st_mode | stat.S_IEXEC)

            context = HookContext(
                spec_name="test",
                task_group="1",
                workspace=str(base),
                branch="feature/test",
            )

            result = run_hook(str(script_path), context, mode=mode)
            assert result.exit_code == 0
