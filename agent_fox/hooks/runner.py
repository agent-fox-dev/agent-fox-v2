"""Hook runner: execute user-configured scripts at lifecycle boundaries.

Handles pre-session, post-session, and sync-barrier hook scripts with
configurable failure modes (abort/warn) and timeouts.

Requirements: 06-REQ-1.1, 06-REQ-1.2, 06-REQ-2.1, 06-REQ-2.2, 06-REQ-2.3,
              06-REQ-3.1, 06-REQ-3.2, 06-REQ-4.1, 06-REQ-4.2, 06-REQ-5.1
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agent_fox.core.config import HookConfig
from agent_fox.core.errors import HookError

logger = logging.getLogger("agent_fox.hooks.runner")


@dataclass(frozen=True)
class HookContext:
    """Context passed to hook scripts via environment variables."""

    spec_name: str
    task_group: str  # group number as string, or barrier sequence
    workspace: str  # absolute path to workspace directory
    branch: str  # feature branch name


@dataclass(frozen=True)
class HookResult:
    """Result of a single hook script execution."""

    script: str  # path or name of the hook script
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool


def build_hook_env(context: HookContext) -> dict[str, str]:
    """Build the environment variable dict for a hook subprocess.

    Returns a copy of the current environment with AF_* variables added:
    - AF_SPEC_NAME: the current specification name
    - AF_TASK_GROUP: the current task group number
    - AF_WORKSPACE: absolute path to the workspace directory
    - AF_BRANCH: the feature branch name
    """
    env = os.environ.copy()
    env["AF_SPEC_NAME"] = context.spec_name
    env["AF_TASK_GROUP"] = context.task_group
    env["AF_WORKSPACE"] = context.workspace
    env["AF_BRANCH"] = context.branch
    return env


def run_hook(
    script: str,
    context: HookContext,
    *,
    timeout: int = 300,
    mode: str = "abort",
    cwd: Path | None = None,
) -> HookResult:
    """Execute a single hook script as a subprocess.

    Args:
        script: Path to the hook script or command string.
        context: HookContext with task metadata.
        timeout: Maximum execution time in seconds.
        mode: "abort" or "warn" -- determines behavior on failure.
        cwd: Working directory for the subprocess.

    Returns:
        HookResult with exit code, output, and timeout flag.

    Raises:
        HookError: If the hook fails and mode is "abort".
    """
    env = build_hook_env(context)
    cwd_str = str(cwd) if cwd is not None else None

    try:
        completed = subprocess.run(
            [script],
            env=env,
            cwd=cwd_str,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        result = HookResult(
            script=script,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        result = HookResult(
            script=script,
            exit_code=-1,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            timed_out=True,
        )
    except FileNotFoundError:
        result = HookResult(
            script=script,
            exit_code=127,
            stdout="",
            stderr=f"Hook script not found: {script}",
            timed_out=False,
        )
    except OSError as exc:
        result = HookResult(
            script=script,
            exit_code=126,
            stdout="",
            stderr=f"Hook script not executable or OS error: {script}: {exc}",
            timed_out=False,
        )

    # Handle failure based on mode
    if result.exit_code != 0:
        if mode == "abort":
            if result.timed_out:
                raise HookError(
                    f"Hook script '{script}' timed out after {timeout}s",
                    script=script,
                    timeout=timeout,
                )
            raise HookError(
                f"Hook script '{script}' failed with exit code {result.exit_code}",
                script=script,
                exit_code=result.exit_code,
            )
        # mode == "warn"
        if result.timed_out:
            logger.warning(
                "Hook script '%s' timed out after %ds (warn mode, continuing)",
                script,
                timeout,
            )
        else:
            logger.warning(
                "Hook script '%s' failed with exit code %d (warn mode, continuing)",
                script,
                result.exit_code,
            )

    return result


def run_hooks(
    scripts: list[str],
    context: HookContext,
    *,
    config: HookConfig,
    cwd: Path | None = None,
) -> list[HookResult]:
    """Execute a list of hook scripts sequentially.

    Args:
        scripts: List of hook script paths/commands.
        context: HookContext with task metadata.
        config: HookConfig for timeout and per-hook modes.
        cwd: Working directory for subprocesses.

    Returns:
        List of HookResult for each script executed.

    Raises:
        HookError: If any hook fails in "abort" mode.
    """
    results: list[HookResult] = []
    for script in scripts:
        # Look up per-hook mode, defaulting to "abort" (06-REQ-2.3)
        mode = config.modes.get(script, "abort")
        result = run_hook(
            script,
            context,
            timeout=config.timeout,
            mode=mode,
            cwd=cwd,
        )
        results.append(result)
    return results


def run_pre_session_hooks(
    context: HookContext,
    config: HookConfig,
    *,
    no_hooks: bool = False,
) -> list[HookResult]:
    """Run all configured pre-session hooks.

    Args:
        context: HookContext with task metadata.
        config: HookConfig with pre_code script list.
        no_hooks: If True, skip all hooks and return empty list.

    Returns:
        List of HookResult. Empty if no_hooks=True or no hooks configured.

    Raises:
        HookError: If any abort-mode hook fails.
    """
    if no_hooks or not config.pre_code:
        return []
    return run_hooks(
        config.pre_code,
        context,
        config=config,
        cwd=Path(context.workspace) if context.workspace else None,
    )


def run_post_session_hooks(
    context: HookContext,
    config: HookConfig,
    *,
    no_hooks: bool = False,
) -> list[HookResult]:
    """Run all configured post-session hooks.

    Args:
        context: HookContext with task metadata.
        config: HookConfig with post_code script list.
        no_hooks: If True, skip all hooks and return empty list.

    Returns:
        List of HookResult. Empty if no_hooks=True or no hooks configured.

    Raises:
        HookError: If any abort-mode hook fails.
    """
    if no_hooks or not config.post_code:
        return []
    return run_hooks(
        config.post_code,
        context,
        config=config,
        cwd=Path(context.workspace) if context.workspace else None,
    )


def run_sync_barrier_hooks(
    barrier_number: int,
    config: HookConfig,
    *,
    workspace: str = "",
    branch: str = "",
    no_hooks: bool = False,
) -> list[HookResult]:
    """Run all configured sync-barrier hooks.

    Creates a HookContext with spec_name="__sync_barrier__" and
    task_group set to the barrier sequence number.

    Args:
        barrier_number: The barrier sequence number (1, 2, 3, ...).
        config: HookConfig with sync_barrier script list.
        workspace: Workspace path for the barrier context.
        branch: Branch name for the barrier context.
        no_hooks: If True, skip all hooks and return empty list.

    Returns:
        List of HookResult. Empty if no_hooks=True or no hooks configured.

    Raises:
        HookError: If any abort-mode hook fails.
    """
    if no_hooks or not config.sync_barrier:
        return []

    context = HookContext(
        spec_name="__sync_barrier__",
        task_group=str(barrier_number),
        workspace=workspace,
        branch=branch,
    )
    return run_hooks(
        config.sync_barrier,
        context,
        config=config,
        cwd=Path(workspace) if workspace else None,
    )
