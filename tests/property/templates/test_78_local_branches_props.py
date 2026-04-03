"""Property-based tests for local-only feature branch workflow — spec 78.

Test Spec: TS-78-P1 through TS-78-P4
Requirements: 78-REQ-1.1, 78-REQ-1.2, 78-REQ-1.E1, 78-REQ-2.1, 78-REQ-2.2,
              78-REQ-3.1, 78-REQ-3.2
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

try:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

from agent_fox.workspace import WorkspaceInfo
from agent_fox.workspace.harvest import post_harvest_integrate

pytestmark = pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")

# ---------------------------------------------------------------------------
# Resolve template paths relative to this file
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parents[3]
_AGENTS_MD_TEMPLATE = _REPO_ROOT / "agent_fox" / "_templates" / "agents_md.md"
_AF_SPEC_TEMPLATE = _REPO_ROOT / "agent_fox" / "_templates" / "skills" / "af-spec"


# ---------------------------------------------------------------------------
# Strategy: generate valid feature branch names
# ---------------------------------------------------------------------------

_feature_branch_strategy = st.from_regex(r"feature/[a-z_]+/[0-9]+", fullmatch=True)


def _run(coro):
    """Run a coroutine in a fresh event loop (compatible with Python 3.12+)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# TS-78-P1: Post-harvest never calls push_to_remote directly
# ---------------------------------------------------------------------------


@given(branch=_feature_branch_strategy)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_never_pushes_feature(branch: str) -> None:
    """Property: for any branch name, push_to_remote is never called directly.

    Test Spec: TS-78-P1
    Requirements: 78-REQ-1.1, 78-REQ-1.3
    """
    workspace = WorkspaceInfo(
        path=Path("/tmp/test-worktree"),
        branch=branch,
        spec_name="test_spec",
        task_group=1,
    )
    mock_push_remote = AsyncMock(return_value=True)

    with (
        patch(
            "agent_fox.workspace.harvest.push_to_remote",
            mock_push_remote,
        ),
        patch(
            "agent_fox.workspace.harvest._push_develop_if_pushable",
            new_callable=AsyncMock,
        ),
    ):
        _run(
            post_harvest_integrate(
                repo_root=Path("/tmp/repo"),
                workspace=workspace,
            )
        )

    assert mock_push_remote.call_count == 0, (
        f"push_to_remote was called {mock_push_remote.call_count} time(s) for branch {branch!r}"
    )


# ---------------------------------------------------------------------------
# TS-78-P2: Post-harvest always calls _push_develop_if_pushable
# ---------------------------------------------------------------------------


@given(branch=_feature_branch_strategy)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_always_pushes_develop(branch: str) -> None:
    """Property: for any branch name, _push_develop_if_pushable is always called.

    Test Spec: TS-78-P2
    Requirements: 78-REQ-1.2, 78-REQ-1.E1
    """
    workspace = WorkspaceInfo(
        path=Path("/tmp/test-worktree"),
        branch=branch,
        spec_name="test_spec",
        task_group=1,
    )
    repo_root = Path("/tmp/repo")

    with (
        patch(
            "agent_fox.workspace.harvest._push_develop_if_pushable",
            new_callable=AsyncMock,
        ) as mock_push_develop,
    ):
        _run(
            post_harvest_integrate(
                repo_root=repo_root,
                workspace=workspace,
            )
        )

    mock_push_develop.assert_called_once_with(repo_root)


# ---------------------------------------------------------------------------
# TS-78-P3: Agent template has no feature branch push instructions
# ---------------------------------------------------------------------------


def test_agent_template_no_push() -> None:
    """Property: agents_md.md never instructs pushing feature branches.

    Test Spec: TS-78-P3
    Requirements: 78-REQ-2.1, 78-REQ-2.2
    """
    content = _AGENTS_MD_TEMPLATE.read_text()
    assert "pushed to `origin`" not in content, "agents_md.md still contains 'pushed to `origin`'"
    assert "push the feature branch" not in content, "agents_md.md still contains 'push the feature branch'"


# ---------------------------------------------------------------------------
# TS-78-P4: Spec template has no feature branch push instructions
# ---------------------------------------------------------------------------


def test_spec_template_no_push() -> None:
    """Property: af-spec template does not reference pushing feature branches.

    Test Spec: TS-78-P4
    Requirements: 78-REQ-3.1, 78-REQ-3.2
    """
    content = _AF_SPEC_TEMPLATE.read_text()
    assert "pushed to remote" not in content, "af-spec still contains 'pushed to remote'"
