"""Tests for predictive file conflict detection.

Test Spec: TS-39-26, TS-39-27, TS-39-28, TS-39-E2
Requirements: 39-REQ-9.1, 39-REQ-9.2, 39-REQ-9.3, 39-REQ-9.E1
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# TS-39-26: File Impact Extraction
# ---------------------------------------------------------------------------


class TestFileImpacts:
    """TS-39-26, TS-39-27, TS-39-28, TS-39-E2: File impact detection.

    Requirements: 39-REQ-9.1, 39-REQ-9.2, 39-REQ-9.3, 39-REQ-9.E1
    """

    def test_extract_impacts(self, tmp_path: Path) -> None:
        """TS-39-26: File impacts extracted from spec documents.

        Requirement: 39-REQ-9.1
        """
        from agent_fox.graph.file_impacts import extract_file_impacts

        # Create a mock tasks.md referencing files
        tasks_md = tmp_path / "tasks.md"
        tasks_md.write_text(
            "## Tasks\n"
            "- [ ] 1. Write tests\n"
            "  - [ ] 1.1 Create `routing/duration.py`\n"
            "  - [ ] 1.2 Update `engine/graph_sync.py`\n"
        )

        impacts = extract_file_impacts(tmp_path, task_group=1)
        assert "routing/duration.py" in impacts
        assert "engine/graph_sync.py" in impacts

    def test_detect_conflicts(self) -> None:
        """TS-39-27: Overlapping predicted files flagged as conflicts.

        Requirement: 39-REQ-9.2
        """
        from agent_fox.graph.file_impacts import FileImpact, detect_conflicts

        impacts = [
            FileImpact("a", {"f1", "f2"}),
            FileImpact("b", {"f2", "f3"}),
        ]
        conflicts = detect_conflicts(impacts)
        assert len(conflicts) == 1
        assert conflicts[0] == ("a", "b", {"f2"})

    def test_no_conflicts_disjoint(self) -> None:
        """No conflicts when file sets are disjoint."""
        from agent_fox.graph.file_impacts import FileImpact, detect_conflicts

        impacts = [
            FileImpact("a", {"f1"}),
            FileImpact("b", {"f2"}),
        ]
        conflicts = detect_conflicts(impacts)
        assert len(conflicts) == 0

    def test_serialize_conflicting(self) -> None:
        """TS-39-28: Conflicting tasks are serialized in dispatch.

        Requirement: 39-REQ-9.3
        """
        from agent_fox.graph.file_impacts import (
            FileImpact,
            filter_conflicts_from_dispatch,
        )

        ready = ["a", "b", "c"]
        impacts = [
            FileImpact("a", {"shared.py"}),
            FileImpact("b", {"shared.py"}),
            FileImpact("c", {"other.py"}),
        ]

        dispatched = filter_conflicts_from_dispatch(ready, impacts)
        # Both a and b conflict; only one should be dispatched
        assert not ("a" in dispatched and "b" in dispatched)
        # c is non-conflicting and should be dispatched
        assert "c" in dispatched

    def test_no_impacts_non_conflicting(self, tmp_path: Path) -> None:
        """TS-39-E2: No extractable file impacts treated as non-conflicting.

        Requirement: 39-REQ-9.E1
        """
        from agent_fox.graph.file_impacts import (
            FileImpact,
            detect_conflicts,
            extract_file_impacts,
        )

        # Empty tasks.md with no file references
        tasks_md = tmp_path / "tasks.md"
        tasks_md.write_text("## Tasks\n- [ ] 1. Do something\n")

        impacts = extract_file_impacts(tmp_path, task_group=1)
        assert impacts == set()

        conflicts = detect_conflicts([
            FileImpact("a", impacts),
            FileImpact("b", {"f1"}),
        ])
        assert len(conflicts) == 0

    def test_multiple_conflicts(self) -> None:
        """Multiple conflict pairs detected."""
        from agent_fox.graph.file_impacts import FileImpact, detect_conflicts

        impacts = [
            FileImpact("a", {"f1", "f2"}),
            FileImpact("b", {"f2", "f3"}),
            FileImpact("c", {"f3", "f4"}),
        ]
        conflicts = detect_conflicts(impacts)
        # a-b overlap on f2, b-c overlap on f3
        assert len(conflicts) == 2
