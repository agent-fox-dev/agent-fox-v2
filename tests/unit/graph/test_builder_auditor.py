"""Tests for auditor test-writing group detection and auto-mid injection.

Test Spec: TS-46-7 through TS-46-16, TS-46-E1, TS-46-E4, TS-46-E5,
           TS-46-P1, TS-46-P2, TS-46-P3
Requirements: 46-REQ-3.*, 46-REQ-4.*
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

try:
    from hypothesis import assume, given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


def _tgd(number: int, title: str = "T", **kw):
    """Build a TaskGroupDef with short defaults."""
    from agent_fox.spec.parser import TaskGroupDef

    defaults = dict(optional=False, completed=False, subtasks=(), body="")
    defaults.update(kw)
    return TaskGroupDef(number=number, title=title, **defaults)


def _spec(name: str = "spec"):
    """Build a SpecInfo with short defaults."""
    from agent_fox.spec.discovery import SpecInfo

    return SpecInfo(
        name=name,
        prefix=0,
        path=Path(f".specs/{name}"),
        has_tasks=True,
        has_prd=False,
    )


# ---------------------------------------------------------------------------
# TS-46-7: Detection Matches Known Patterns
# Requirements: 46-REQ-3.1, 46-REQ-3.2
# ---------------------------------------------------------------------------


class TestDetectionMatches:
    """Verify is_test_writing_group detects all specified patterns."""

    def test_detection_matches(self) -> None:
        from agent_fox.graph.builder import is_test_writing_group

        assert is_test_writing_group("Write failing spec tests") is True
        assert is_test_writing_group("Write failing tests") is True
        assert is_test_writing_group("Create unit test files") is True
        assert is_test_writing_group("Create test file structure") is True
        assert is_test_writing_group("1. Spec tests") is True


# ---------------------------------------------------------------------------
# TS-46-8: Detection Case Insensitive
# Requirement: 46-REQ-3.1
# ---------------------------------------------------------------------------


class TestDetectionCaseInsensitive:
    """Verify detection is case-insensitive."""

    def test_detection_case_insensitive(self) -> None:
        from agent_fox.graph.builder import is_test_writing_group

        assert is_test_writing_group("WRITE FAILING SPEC TESTS") is True
        assert is_test_writing_group("write Failing Spec Tests") is True


# ---------------------------------------------------------------------------
# TS-46-9: Detection Rejects Non-Test Groups
# Requirement: 46-REQ-3.E1
# ---------------------------------------------------------------------------


class TestDetectionRejects:
    """Verify is_test_writing_group returns False for non-test groups."""

    def test_detection_rejects(self) -> None:
        from agent_fox.graph.builder import is_test_writing_group

        assert is_test_writing_group("Implement core module") is False
        assert is_test_writing_group("Refactor database layer") is False
        assert is_test_writing_group("Phase A checkpoint") is False


# ---------------------------------------------------------------------------
# TS-46-10: Detection Matches Substrings
# Requirement: 46-REQ-3.E2
# ---------------------------------------------------------------------------


class TestDetectionSubstring:
    """Verify detection matches patterns as substrings."""

    def test_detection_substring(self) -> None:
        from agent_fox.graph.builder import is_test_writing_group

        assert is_test_writing_group("Write failing spec tests for module X") is True


# ---------------------------------------------------------------------------
# TS-46-11: Auto-Mid Injection Creates Node and Edges
# Requirements: 46-REQ-4.1, 46-REQ-4.2, 46-REQ-4.3
# ---------------------------------------------------------------------------


class TestAutoMidInjection:
    """Verify auto_mid injection inserts auditor node with correct edges."""

    def test_auto_mid_injection(self, tmp_path: Path) -> None:
        from agent_fox.core.config import ArchetypesConfig, AuditorConfig
        from agent_fox.graph.builder import build_graph

        # Create a test_spec.md with enough TS entries
        spec_dir = tmp_path / ".specs" / "spec"
        spec_dir.mkdir(parents=True)
        ts_content = "\n".join(
            f"### TS-46-{i}\nDescription {i}\n" for i in range(1, 8)
        )
        (spec_dir / "test_spec.md").write_text(ts_content)

        config = ArchetypesConfig(
            auditor=True,
            auditor_config=AuditorConfig(min_ts_entries=5),
        )
        spec = _spec("spec")
        spec.path = spec_dir
        specs = [spec]
        task_groups = {
            "spec": [
                _tgd(1, "Write failing spec tests"),
                _tgd(2, "Implement core"),
            ],
        }

        graph = build_graph(specs, task_groups, [], archetypes_config=config)

        auditor_nodes = [
            n for n in graph.nodes.values() if n.archetype == "auditor"
        ]
        assert len(auditor_nodes) == 1

        auditor_node = auditor_nodes[0]
        # Verify edges: group 1 -> auditor -> group 2
        assert any(
            e.source == "spec:1" and e.target == auditor_node.id
            for e in graph.edges
        )
        assert any(
            e.source == auditor_node.id and e.target == "spec:2"
            for e in graph.edges
        )
        assert auditor_node.instances == config.instances.auditor


# ---------------------------------------------------------------------------
# TS-46-12: Injection Skipped When Disabled
# Requirement: 46-REQ-4.E1
# ---------------------------------------------------------------------------


class TestInjectionDisabled:
    """Verify no auditor injection when auditor is disabled."""

    def test_injection_disabled(self) -> None:
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        config = ArchetypesConfig(auditor=False)
        specs = [_spec()]
        task_groups = {
            "spec": [
                _tgd(1, "Write failing spec tests"),
                _tgd(2, "Implement"),
            ],
        }

        graph = build_graph(specs, task_groups, [], archetypes_config=config)

        auditor_nodes = [
            n for n in graph.nodes.values() if n.archetype == "auditor"
        ]
        assert len(auditor_nodes) == 0


# ---------------------------------------------------------------------------
# TS-46-13: Injection Skipped Below TS Threshold
# Requirement: 46-REQ-4.4
# ---------------------------------------------------------------------------


class TestInjectionSkippedBelowThreshold:
    """Verify injection skipped when TS entry count is below threshold."""

    def test_injection_skipped_below_threshold(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture,
    ) -> None:
        from agent_fox.core.config import ArchetypesConfig, AuditorConfig
        from agent_fox.graph.builder import build_graph

        # Create test_spec.md with only 3 TS entries (below threshold of 5)
        spec_dir = tmp_path / ".specs" / "spec"
        spec_dir.mkdir(parents=True)
        ts_content = "\n".join(
            f"### TS-46-{i}\nDescription {i}\n" for i in range(1, 4)
        )
        (spec_dir / "test_spec.md").write_text(ts_content)

        config = ArchetypesConfig(
            auditor=True,
            auditor_config=AuditorConfig(min_ts_entries=5),
        )
        spec = _spec("spec")
        spec.path = spec_dir
        specs = [spec]
        task_groups = {
            "spec": [
                _tgd(1, "Write failing spec tests"),
                _tgd(2, "Implement"),
            ],
        }

        with caplog.at_level(logging.INFO):
            graph = build_graph(specs, task_groups, [], archetypes_config=config)

        auditor_nodes = [
            n for n in graph.nodes.values() if n.archetype == "auditor"
        ]
        assert len(auditor_nodes) == 0
        assert any("skip" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# TS-46-14: Injection When Test Group Is Last
# Requirement: 46-REQ-4.E2
# ---------------------------------------------------------------------------


class TestInjectionLastGroup:
    """Verify auditor node injected after last group with no successor."""

    def test_injection_last_group(self, tmp_path: Path) -> None:
        from agent_fox.core.config import ArchetypesConfig, AuditorConfig
        from agent_fox.graph.builder import build_graph

        spec_dir = tmp_path / ".specs" / "spec"
        spec_dir.mkdir(parents=True)
        ts_content = "\n".join(
            f"### TS-46-{i}\nDescription {i}\n" for i in range(1, 8)
        )
        (spec_dir / "test_spec.md").write_text(ts_content)

        config = ArchetypesConfig(
            auditor=True,
            auditor_config=AuditorConfig(min_ts_entries=5),
        )
        spec = _spec("spec")
        spec.path = spec_dir
        specs = [spec]
        # Only one group, and it's the test-writing group (last)
        task_groups = {
            "spec": [_tgd(1, "Write failing spec tests")],
        }

        graph = build_graph(specs, task_groups, [], archetypes_config=config)

        auditor_nodes = [
            n for n in graph.nodes.values() if n.archetype == "auditor"
        ]
        assert len(auditor_nodes) == 1

        auditor_node = auditor_nodes[0]
        # Should have incoming edge from group 1
        assert any(
            e.source == "spec:1" and e.target == auditor_node.id
            for e in graph.edges
        )
        # No outgoing edge from auditor
        outgoing = [e for e in graph.edges if e.source == auditor_node.id]
        assert len(outgoing) == 0


# ---------------------------------------------------------------------------
# TS-46-15: Coexistence With Skeptic
# Requirement: 46-REQ-4.E3
# ---------------------------------------------------------------------------


class TestCoexistenceSkeptic:
    """Verify both skeptic and auditor inject without conflict."""

    def test_coexistence_skeptic(self, tmp_path: Path) -> None:
        from agent_fox.core.config import ArchetypesConfig, AuditorConfig
        from agent_fox.graph.builder import build_graph

        spec_dir = tmp_path / ".specs" / "spec"
        spec_dir.mkdir(parents=True)
        ts_content = "\n".join(
            f"### TS-46-{i}\nDescription {i}\n" for i in range(1, 8)
        )
        (spec_dir / "test_spec.md").write_text(ts_content)

        config = ArchetypesConfig(
            skeptic=True,
            auditor=True,
            auditor_config=AuditorConfig(min_ts_entries=5),
        )
        spec = _spec("spec")
        spec.path = spec_dir
        specs = [spec]
        task_groups = {
            "spec": [
                _tgd(1, "Write failing spec tests"),
                _tgd(2, "Implement core"),
            ],
        }

        graph = build_graph(specs, task_groups, [], archetypes_config=config)

        skeptic_nodes = [
            n for n in graph.nodes.values() if n.archetype == "skeptic"
        ]
        auditor_nodes = [
            n for n in graph.nodes.values() if n.archetype == "auditor"
        ]
        assert len(skeptic_nodes) >= 1
        assert len(auditor_nodes) >= 1


# ---------------------------------------------------------------------------
# TS-46-16: Multiple Test Groups Get Multiple Auditors
# Requirement: 46-REQ-3.3
# ---------------------------------------------------------------------------


class TestMultipleTestGroups:
    """Verify auditor node injected after each test-writing group."""

    def test_multiple_test_groups(self, tmp_path: Path) -> None:
        from agent_fox.core.config import ArchetypesConfig, AuditorConfig
        from agent_fox.graph.builder import build_graph

        spec_dir = tmp_path / ".specs" / "spec"
        spec_dir.mkdir(parents=True)
        ts_content = "\n".join(
            f"### TS-46-{i}\nDescription {i}\n" for i in range(1, 8)
        )
        (spec_dir / "test_spec.md").write_text(ts_content)

        config = ArchetypesConfig(
            auditor=True,
            auditor_config=AuditorConfig(min_ts_entries=5),
        )
        spec = _spec("spec")
        spec.path = spec_dir
        specs = [spec]
        task_groups = {
            "spec": [
                _tgd(1, "Write failing spec tests"),
                _tgd(2, "Implement core"),
                _tgd(3, "Create unit test files"),
                _tgd(4, "Implement extras"),
            ],
        }

        graph = build_graph(specs, task_groups, [], archetypes_config=config)

        auditor_nodes = [
            n for n in graph.nodes.values() if n.archetype == "auditor"
        ]
        assert len(auditor_nodes) == 2


# ---------------------------------------------------------------------------
# TS-46-E1: No Test Groups Detected
# Requirement: 46-REQ-3.E1
# ---------------------------------------------------------------------------


class TestNoTestGroupsDetected:
    """Verify no auditor injection when no test-writing groups exist."""

    def test_no_test_groups(self) -> None:
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        config = ArchetypesConfig(auditor=True)
        specs = [_spec()]
        task_groups = {
            "spec": [
                _tgd(1, "Implement core module"),
                _tgd(2, "Refactor database layer"),
            ],
        }

        graph = build_graph(specs, task_groups, [], archetypes_config=config)

        auditor_nodes = [
            n for n in graph.nodes.values() if n.archetype == "auditor"
        ]
        assert len(auditor_nodes) == 0


# ---------------------------------------------------------------------------
# TS-46-E4: TS Entry Count Function
# Requirement: 46-REQ-4.4
# ---------------------------------------------------------------------------


class TestTSEntryCount:
    """Verify count_ts_entries correctly counts TS entries."""

    def test_ts_entry_count(self, tmp_path: Path) -> None:
        from agent_fox.graph.builder import count_ts_entries

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        ts_content = "\n".join(
            f"### TS-46-{i}\nDescription {i}\n" for i in range(1, 8)
        )
        (spec_dir / "test_spec.md").write_text(ts_content)

        count = count_ts_entries(spec_dir)
        assert count == 7


# ---------------------------------------------------------------------------
# TS-46-E5: TS Entry Count Missing File
# Requirement: 46-REQ-4.4
# ---------------------------------------------------------------------------


class TestTSEntryCountMissing:
    """Verify count_ts_entries returns 0 for missing file."""

    def test_ts_entry_count_missing(self, tmp_path: Path) -> None:
        from agent_fox.graph.builder import count_ts_entries

        count = count_ts_entries(tmp_path)
        assert count == 0


# ---------------------------------------------------------------------------
# TS-46-P1: Detection Completeness (Property)
# Property 1: Any string containing a test-writing pattern is detected.
# Validates: 46-REQ-3.1, 46-REQ-3.2, 46-REQ-3.E2
# ---------------------------------------------------------------------------

_KNOWN_PATTERNS = [
    "write failing spec tests",
    "write failing tests",
    "create unit test",
    "create test file",
    "spec tests",
]


class TestPropertyDetectionCompleteness:
    """Any string containing a test-writing pattern is detected."""

    @pytest.mark.skipif(
        not HAS_HYPOTHESIS, reason="hypothesis not installed",
    )
    @given(
        prefix=st.text(max_size=20),
        pattern=st.sampled_from(_KNOWN_PATTERNS),
        suffix=st.text(max_size=20),
    )
    @settings(max_examples=50)
    def test_prop_detection_completeness(
        self, prefix: str, pattern: str, suffix: str,
    ) -> None:
        from agent_fox.graph.builder import is_test_writing_group

        title = prefix + pattern + suffix
        assert is_test_writing_group(title) is True


# ---------------------------------------------------------------------------
# TS-46-P2: Detection Specificity (Property)
# Property 2: Strings not containing any pattern are not detected.
# Validates: 46-REQ-3.1, 46-REQ-3.E1
# ---------------------------------------------------------------------------


class TestPropertyDetectionSpecificity:
    """Strings not containing any pattern are not detected."""

    @pytest.mark.skipif(
        not HAS_HYPOTHESIS, reason="hypothesis not installed",
    )
    @given(
        title=st.text(
            alphabet=st.characters(whitelist_categories=("L",)),
            max_size=50,
        ),
    )
    @settings(max_examples=50)
    def test_prop_detection_specificity(self, title: str) -> None:
        from agent_fox.graph.builder import is_test_writing_group

        # Skip if the generated text happens to contain a pattern
        lower = title.lower()
        for pattern in _KNOWN_PATTERNS:
            assume(pattern not in lower)

        assert is_test_writing_group(title) is False


# ---------------------------------------------------------------------------
# TS-46-P3: Injection Graph Integrity (Property)
# Property 3: Injected auditor nodes have correct edge structure.
# Validates: 46-REQ-4.1, 46-REQ-4.2, 46-REQ-4.3, 46-REQ-4.E2
# ---------------------------------------------------------------------------


class TestPropertyInjectionIntegrity:
    """Injected auditor nodes have correct edge structure."""

    @pytest.mark.skipif(
        not HAS_HYPOTHESIS, reason="hypothesis not installed",
    )
    @given(
        n_groups=st.integers(min_value=1, max_value=5),
        test_group_idx=st.data(),
    )
    @settings(max_examples=15)
    def test_prop_injection_integrity(
        self, n_groups: int, test_group_idx: st.DataObject, tmp_path: Path,
    ) -> None:
        from agent_fox.core.config import ArchetypesConfig, AuditorConfig
        from agent_fox.graph.builder import build_graph

        idx = test_group_idx.draw(
            st.integers(min_value=0, max_value=n_groups - 1)
        )

        # Create test_spec.md with enough entries
        spec_dir = tmp_path / ".specs" / "spec"
        spec_dir.mkdir(parents=True, exist_ok=True)
        ts_content = "\n".join(
            f"### TS-46-{i}\nDescription {i}\n" for i in range(1, 8)
        )
        (spec_dir / "test_spec.md").write_text(ts_content)

        config = ArchetypesConfig(
            auditor=True,
            auditor_config=AuditorConfig(min_ts_entries=5),
        )
        spec = _spec("spec")
        spec.path = spec_dir

        groups = []
        for i in range(n_groups):
            if i == idx:
                groups.append(_tgd(i + 1, "Write failing spec tests"))
            else:
                groups.append(_tgd(i + 1, f"Implement group {i + 1}"))

        task_groups = {"spec": groups}

        graph = build_graph(
            [spec], task_groups, [], archetypes_config=config,
        )

        auditor_nodes = [
            n for n in graph.nodes.values() if n.archetype == "auditor"
        ]
        assert len(auditor_nodes) == 1

        auditor_node = auditor_nodes[0]
        incoming = [e for e in graph.edges if e.target == auditor_node.id]
        outgoing = [e for e in graph.edges if e.source == auditor_node.id]

        assert len(incoming) == 1
        assert len(outgoing) <= 1
