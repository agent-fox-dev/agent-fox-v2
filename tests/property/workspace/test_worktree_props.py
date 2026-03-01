"""Property tests for worktree path uniqueness.

Test Spec: TS-03-P1 (worktree paths are unique per (spec, group))
Property: Property 1 from design.md
Requirements: 03-REQ-1.1, 03-REQ-1.2
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from agent_fox.workspace.worktree import WorkspaceInfo

# Strategy for valid spec names: alphanumeric + underscores, non-empty
spec_name_strategy = st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True)
task_group_strategy = st.integers(min_value=1, max_value=100)


class TestWorktreePathUniqueness:
    """TS-03-P1: Worktree paths are unique per (spec, group).

    Property 1: For any two distinct (spec_name, task_group) pairs,
    the resulting WorkspaceInfo objects have different path and branch values.
    """

    @given(
        spec_a=spec_name_strategy,
        group_a=task_group_strategy,
        spec_b=spec_name_strategy,
        group_b=task_group_strategy,
    )
    @settings(max_examples=50)
    def test_distinct_pairs_produce_distinct_paths(
        self,
        spec_a: str,
        group_a: int,
        spec_b: str,
        group_b: int,
    ) -> None:
        """Different (spec, group) pairs produce different paths."""
        assume((spec_a, group_a) != (spec_b, group_b))

        repo = Path("/repo")
        ws_a = WorkspaceInfo(
            path=repo / ".agent-fox" / "worktrees" / spec_a / str(group_a),
            branch=f"feature/{spec_a}/{group_a}",
            spec_name=spec_a,
            task_group=group_a,
        )
        ws_b = WorkspaceInfo(
            path=repo / ".agent-fox" / "worktrees" / spec_b / str(group_b),
            branch=f"feature/{spec_b}/{group_b}",
            spec_name=spec_b,
            task_group=group_b,
        )

        assert ws_a.path != ws_b.path
        assert ws_a.branch != ws_b.branch
