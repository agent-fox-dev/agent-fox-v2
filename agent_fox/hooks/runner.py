"""Hook runner: execute user-configured scripts at lifecycle boundaries.

Handles pre-session, post-session, and sync-barrier hook scripts with
configurable failure modes (abort/warn) and timeouts.

Requirements: 06-REQ-1.1, 06-REQ-1.2, 06-REQ-2.1, 06-REQ-2.2, 06-REQ-2.3,
              06-REQ-3.1, 06-REQ-3.2, 06-REQ-4.1, 06-REQ-4.2, 06-REQ-5.1
"""

from __future__ import annotations

import logging
import subprocess  # noqa: F401
from dataclasses import dataclass
from pathlib import Path

from agent_fox.core.config import HookConfig
from agent_fox.core.errors import HookError  # noqa: F401

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
    raise NotImplementedError


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
    raise NotImplementedError


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
    raise NotImplementedError


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
    raise NotImplementedError


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
    raise NotImplementedError


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
    raise NotImplementedError
