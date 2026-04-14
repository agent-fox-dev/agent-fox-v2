"""Verification tests for JsonlSink removal.

These tests assert the desired end state after task group 3 changes:
  - TS-103-12: jsonl_sink.py does NOT exist
  - TS-103-13: no jsonl_sink imports remain in agent_fox/ source

Test Spec: TS-103-12, TS-103-13
Requirements: 103-REQ-7.1, 103-REQ-7.E1
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# TS-103-12: JsonlSink module removed
# ---------------------------------------------------------------------------

# Repo root is 3 levels above this file:
# tests/unit/knowledge/test_agent_trace_removal.py → parents[3] = repo root
_REPO_ROOT = Path(__file__).parents[3]
_JSONL_SINK_MODULE = _REPO_ROOT / "agent_fox" / "knowledge" / "jsonl_sink.py"


class TestJsonlSinkModuleRemoval:
    """TS-103-12: Verify JsonlSink module has been removed.

    Requirements: 103-REQ-7.1
    """

    def test_jsonl_sink_module_removed(self) -> None:
        """TS-103-12: agent_fox/knowledge/jsonl_sink.py must not exist."""
        assert not _JSONL_SINK_MODULE.exists(), (
            "jsonl_sink.py was not removed — delete agent_fox/knowledge/jsonl_sink.py"
        )


# ---------------------------------------------------------------------------
# TS-103-13: No jsonl_sink imports remain in agent_fox/
# ---------------------------------------------------------------------------


class TestJsonlSinkImports:
    """TS-103-13: Verify no jsonl_sink import statements remain in agent_fox/.

    Requirements: 103-REQ-7.E1
    """

    def test_no_jsonl_sink_imports(self) -> None:
        """TS-103-13: No agent_fox source file may import from jsonl_sink."""
        agent_fox_dir = _REPO_ROOT / "agent_fox"
        py_files = list(agent_fox_dir.glob("**/*.py"))

        # Look for import statements referencing the deleted module
        _IMPORT_PREFIXES = (
            "from agent_fox.knowledge.jsonl_sink",
            "import agent_fox.knowledge.jsonl_sink",
        )
        import_matches = [
            f
            for f in py_files
            if any(line.strip().startswith(_IMPORT_PREFIXES) for line in f.read_text().splitlines())
        ]

        assert len(import_matches) == 0, (
            f"Found jsonl_sink import statements in: {[str(f) for f in import_matches]}. "
            "Remove all imports of the deleted jsonl_sink module."
        )
