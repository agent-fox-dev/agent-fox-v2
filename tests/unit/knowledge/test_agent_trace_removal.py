"""Verification tests for JsonlSink removal.

These tests assert the CURRENT state of the codebase (before group 3 changes).
In task group 3, the assertions will be INVERTED to assert the desired end state.

Test Spec: TS-103-12, TS-103-13
Requirements: 103-REQ-7.1, 103-REQ-7.E1

NOTE: These tests intentionally pass in group 1 (current state = file exists and
imports are present). They will be flipped in task group 3 to assert:
  - TS-103-12: jsonl_sink.py does NOT exist
  - TS-103-13: no jsonl_sink imports remain in agent_fox/
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# TS-103-12: JsonlSink module status
# ---------------------------------------------------------------------------

# Repo root is 3 levels above this file:
# tests/unit/knowledge/test_agent_trace_removal.py → parents[3] = repo root
_REPO_ROOT = Path(__file__).parents[3]
_JSONL_SINK_MODULE = _REPO_ROOT / "agent_fox" / "knowledge" / "jsonl_sink.py"


class TestJsonlSinkModuleRemoval:
    """TS-103-12: Verify JsonlSink module state.

    Requirements: 103-REQ-7.1

    GROUP 1 STATE: asserts the file EXISTS (current state before removal).
    GROUP 3 INVERSION: will assert the file does NOT exist.
    """

    def test_jsonl_sink_module_removed(self) -> None:
        """TS-103-12 (group 1 state): jsonl_sink.py currently exists.

        TODO (group 3): invert this assertion to:
            assert not _JSONL_SINK_MODULE.exists()
        """
        # Group 1: The file still exists — this will be inverted in group 3.
        assert _JSONL_SINK_MODULE.exists(), "jsonl_sink.py should still exist in group 1 (will be removed in group 3)"


# ---------------------------------------------------------------------------
# TS-103-13: JsonlSink imports status
# ---------------------------------------------------------------------------


class TestJsonlSinkImports:
    """TS-103-13: Verify no (or existing) jsonl_sink imports in agent_fox/.

    Requirements: 103-REQ-7.E1

    GROUP 1 STATE: asserts imports DO exist (current state before cleanup).
    GROUP 3 INVERSION: will assert zero imports remain.
    """

    def test_no_jsonl_sink_imports(self) -> None:
        """TS-103-13 (group 1 state): jsonl_sink imports currently exist.

        TODO (group 3): invert this assertion to:
            assert len(matches) == 0
        """
        agent_fox_dir = _REPO_ROOT / "agent_fox"
        py_files = list(agent_fox_dir.glob("**/*.py"))

        matches = [f for f in py_files if "jsonl_sink" in f.read_text()]

        # Group 1: Imports should exist (run.py imports JsonlSink).
        # This assertion will be inverted in group 3 to assert len(matches) == 0.
        assert len(matches) > 0, "Expected jsonl_sink imports to exist in group 1 (will be cleaned up in group 3)"
