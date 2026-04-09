"""Construct coder session prompts with stub constraint directives.

Requirements: 87-REQ-1.1, 87-REQ-2.3, 87-REQ-5.1
"""

from __future__ import annotations

from agent_fox.scope_guard.models import ScopeCheckResult, TaskGroup


def build_prompt(
    task_group: TaskGroup, scope_result: ScopeCheckResult | None = None
) -> str:
    """Build a coder session prompt for the given task group."""
    raise NotImplementedError
