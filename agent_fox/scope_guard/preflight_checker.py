"""Compare task group deliverables against codebase state.

Requirements: 87-REQ-2.1 through 87-REQ-2.5, 87-REQ-2.E1 through 87-REQ-2.E3
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.scope_guard.models import ScopeCheckResult, TaskGroup


def check_scope(task_group: TaskGroup, codebase_root: Path) -> ScopeCheckResult:
    """Check which deliverables are already implemented in the codebase."""
    raise NotImplementedError
