"""Classify session outcomes based on commit analysis.

Requirements: 87-REQ-1.3, 87-REQ-4.1, 87-REQ-4.E1 through 87-REQ-4.E3
"""

from __future__ import annotations

from agent_fox.scope_guard.models import ScopeGuardSessionOutcome, SessionResult, TaskGroup


def classify_session(
    session: SessionResult, task_group: TaskGroup
) -> ScopeGuardSessionOutcome:
    """Classify a session result into an outcome category."""
    raise NotImplementedError
