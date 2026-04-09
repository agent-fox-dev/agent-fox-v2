"""Analyze specification graph deliverable lists to find scope overlaps.

Requirements: 87-REQ-3.1 through 87-REQ-3.4, 87-REQ-3.E1 through 87-REQ-3.E3
"""

from __future__ import annotations

from agent_fox.scope_guard.models import OverlapResult, SpecGraph


def detect_overlaps(spec_graph: SpecGraph) -> OverlapResult:
    """Detect scope overlaps across task groups in a specification graph."""
    raise NotImplementedError
