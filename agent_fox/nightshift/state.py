"""Night Shift runtime state.

Requirements: 61-REQ-1.E2, 61-REQ-9.3
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NightShiftState:
    """Runtime state for the daemon.

    Mutable -- fields are updated during the daemon lifecycle.
    """

    total_cost: float = 0.0
    total_sessions: int = 0
    issues_created: int = 0
    issues_fixed: int = 0
    hunt_scans_completed: int = 0
    is_shutting_down: bool = False
