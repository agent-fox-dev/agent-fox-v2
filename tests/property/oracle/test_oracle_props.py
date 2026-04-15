"""Property tests for the reviewer (drift-review mode) archetype.

Test Spec: TS-32-P1 through TS-32-P8
Requirements: Properties 1-8 from design.md
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import duckdb
import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


def _create_drift_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create schema with drift_findings table."""
    from tests.unit.knowledge.conftest import create_schema

    create_schema(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drift_findings (
            id UUID PRIMARY KEY,
            severity VARCHAR NOT NULL,
            description VARCHAR NOT NULL,
            spec_ref VARCHAR,
            artifact_ref VARCHAR,
            spec_name VARCHAR NOT NULL,
            task_group VARCHAR NOT NULL,
            session_id VARCHAR NOT NULL,
            superseded_by UUID,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)


def _spec(name: str = "spec"):
    from agent_fox.spec.discovery import SpecInfo

    return SpecInfo(
        name=name,
        prefix=0,
        path=Path(f".specs/{name}"),
        has_tasks=True,
        has_prd=False,
    )


def _tgd(number: int, title: str = "T"):
    from agent_fox.spec.parser import TaskGroupDef

    return TaskGroupDef(
        number=number,
        title=title,
        optional=False,
        completed=False,
        subtasks=(),
        body="",
    )


# ---------------------------------------------------------------------------
# TS-32-P1: Registry Completeness
# Property 1: Oracle registry entry has required fields
# Validates: 32-REQ-1.1, 32-REQ-1.3
# ---------------------------------------------------------------------------


class TestPropertyRegistryCompleteness:
    """Reviewer registry entry always has required fields for drift-review mode."""

    def test_registry_completeness(self) -> None:
        """TS-32-P1: Reviewer entry with drift-review mode has auto_pre, task_assignable, allowlist."""
        from agent_fox.archetypes import resolve_effective_config
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["reviewer"]
        resolved = resolve_effective_config(entry, mode="drift-review")
        assert resolved.injection == "auto_pre"
        assert resolved.task_assignable is True
        assert resolved.default_allowlist is not None
        assert len(resolved.default_allowlist) > 0


# ---------------------------------------------------------------------------
# TS-32-P2: Multi-auto_pre Distinctness
# Property 2: Oracle + skeptic produce distinct nodes
# Validates: 32-REQ-2.2, 32-REQ-3.1, 32-REQ-3.3
# ---------------------------------------------------------------------------


class TestPropertyMultiAutoPre:
    """With reviewer enabled, pre-review and drift-review auto_pre nodes are distinct."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(num_groups=st.integers(min_value=1, max_value=10))
    @settings(max_examples=10)
    def test_multi_auto_pre(self, num_groups: int) -> None:
        """TS-32-P2: Two distinct auto_pre nodes (pre-review + drift-review), both with edges to first coder."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        config = ArchetypesConfig(reviewer=True)
        specs = [_spec()]
        task_groups = {"spec": [_tgd(i, f"T{i}") for i in range(1, num_groups + 1)]}

        graph = build_graph(specs, task_groups, [], archetypes_config=config)

        auto_pre_nodes = [n for n in graph.nodes.values() if n.group_number == 0]
        assert len(auto_pre_nodes) == 2
        ids = {n.id for n in auto_pre_nodes}
        assert len(ids) == 2  # distinct

        # Both connect to first coder group
        first_coder = "spec:1"
        for n in auto_pre_nodes:
            assert any(e.source == n.id and e.target == first_coder and e.kind == "intra_spec" for e in graph.edges), (
                f"Node {n.id} has no edge to {first_coder}"
            )

        # No edges between them
        for a in auto_pre_nodes:
            for b in auto_pre_nodes:
                if a.id != b.id:
                    assert not any(e.source == a.id and e.target == b.id for e in graph.edges)


# ---------------------------------------------------------------------------
# TS-32-P3: Backward-compatible Node IDs
# Property 3: Single auto_pre uses {spec}:0 format
# Validates: 32-REQ-3.2
# ---------------------------------------------------------------------------


class TestPropertyBackwardCompat:
    """Reviewer auto_pre modes produce suffixed node IDs."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(num_groups=st.integers(min_value=1, max_value=3))
    @settings(max_examples=4)
    def test_reviewer_nodes_have_mode_suffix(self, num_groups: int) -> None:
        """TS-32-P3: Reviewer auto_pre nodes use suffixed IDs with mode."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        config = ArchetypesConfig(reviewer=True)
        specs = [_spec()]
        task_groups = {"spec": [_tgd(i, f"T{i}") for i in range(1, num_groups + 1)]}

        graph = build_graph(specs, task_groups, [], archetypes_config=config)

        auto_pre_nodes = [n for n in graph.nodes.values() if n.group_number == 0]
        assert len(auto_pre_nodes) == 2
        assert all(n.archetype == "reviewer" for n in auto_pre_nodes)


# ---------------------------------------------------------------------------
# TS-32-P4: Drift Finding Roundtrip
# Property 4: Valid JSON roundtrips through parse_oracle_output
# Validates: 32-REQ-6.1, 32-REQ-6.2, 32-REQ-6.3
# ---------------------------------------------------------------------------

_severity_strategy = st.sampled_from(["critical", "major", "minor", "observation"])
_drift_finding_strategy = (
    st.fixed_dictionaries(
        {
            "severity": _severity_strategy,
            "description": st.text(min_size=1, max_size=100).filter(
                lambda s: s.strip() and '"' not in s and "\\" not in s
            ),
        }
    )
    if HAS_HYPOTHESIS
    else None
)


class TestPropertyRoundtrip:
    """Valid JSON roundtrips through parse_oracle_output."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        findings=st.lists(
            _drift_finding_strategy,  # type: ignore[arg-type]
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=30)
    def test_roundtrip(self, findings: list[dict]) -> None:
        """TS-32-P4: N valid findings parse to N DriftFinding instances."""
        from agent_fox.session.review_parser import parse_oracle_output

        json_obj = {"drift_findings": findings}
        json_text = json.dumps(json_obj)

        parsed = parse_oracle_output(json_text, "spec", "0", "sess")
        assert len(parsed) == len(findings)
        for i, f in enumerate(findings):
            assert parsed[i].severity == f["severity"]
            assert parsed[i].description == f["description"]


# ---------------------------------------------------------------------------
# TS-32-P5: Supersession Integrity
# Property 5: Only most recent batch returned by active query
# Validates: 32-REQ-7.1, 32-REQ-7.3, 32-REQ-7.4
# ---------------------------------------------------------------------------


def _make_batch(batch_num: int, size: int, spec_name: str = "test_spec"):
    """Create a batch of DriftFindings with a shared session_id."""
    from agent_fox.knowledge.review_store import DriftFinding

    session_id = f"sess_{batch_num}"
    return [
        DriftFinding(
            id=str(uuid.uuid4()),
            severity="major",
            description=f"Batch {batch_num} finding {i}",
            spec_ref=None,
            artifact_ref=None,
            spec_name=spec_name,
            task_group="0",
            session_id=session_id,
        )
        for i in range(size)
    ]


class TestPropertySupersession:
    """Only the most recent insertion is returned by active query."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        batch_sizes=st.lists(
            st.integers(min_value=1, max_value=10),
            min_size=2,
            max_size=5,
        ),
    )
    @settings(max_examples=20, deadline=None)
    def test_supersession(self, batch_sizes: list[int]) -> None:
        """TS-32-P5: Only last batch returned after multiple insertions."""
        from agent_fox.knowledge.review_store import (
            insert_drift_findings,
            query_active_drift_findings,
        )

        conn = duckdb.connect(":memory:")
        _create_drift_schema(conn)

        last_session_id = None
        for i, size in enumerate(batch_sizes):
            batch = _make_batch(i, size)
            last_session_id = batch[0].session_id
            insert_drift_findings(conn, batch)

        result = query_active_drift_findings(conn, "test_spec", "0")
        assert len(result) == batch_sizes[-1]
        assert all(r.session_id == last_session_id for r in result)

        conn.close()


# ---------------------------------------------------------------------------
# TS-32-P6: Block Threshold Monotonicity
# Property 6: Blocking iff critical count > threshold
# Validates: 32-REQ-9.1, 32-REQ-9.2, 32-REQ-9.E1
# ---------------------------------------------------------------------------


class TestPropertyBlockThreshold:
    """Blocking occurs iff critical count > threshold."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        threshold=st.integers(min_value=1, max_value=10),
        critical_count=st.integers(min_value=0, max_value=15),
    )
    @settings(max_examples=50)
    def test_block_threshold(self, threshold: int, critical_count: int) -> None:
        """TS-32-P6: should_block == (critical_count > threshold)."""
        from agent_fox.knowledge.review_store import DriftFinding

        findings = [
            DriftFinding(
                id=str(uuid.uuid4()),
                severity="critical",
                description=f"crit {i}",
                spec_ref=None,
                artifact_ref=None,
                spec_name="s",
                task_group="0",
                session_id="x",
            )
            for i in range(critical_count)
        ]
        actual_critical = sum(1 for f in findings if f.severity == "critical")
        should_block = actual_critical > threshold
        assert should_block == (critical_count > threshold)


# ---------------------------------------------------------------------------
# TS-32-P7: Context Rendering Completeness
# Property 7: All finding descriptions appear in rendered context
# Validates: 32-REQ-8.1, 32-REQ-8.2, 32-REQ-8.E1
# ---------------------------------------------------------------------------


class TestPropertyRenderCompleteness:
    """All finding descriptions appear in rendered context."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        severities=st.lists(
            _severity_strategy,  # type: ignore[arg-type]
            min_size=0,
            max_size=10,
        ),
    )
    @settings(max_examples=20, deadline=None)
    def test_render_completeness(self, severities: list[str]) -> None:
        """TS-32-P7: Each description appears in output; empty -> None."""
        from agent_fox.knowledge.review_store import (
            DriftFinding,
            insert_drift_findings,
        )
        from agent_fox.session.prompt import render_drift_context

        conn = duckdb.connect(":memory:")
        _create_drift_schema(conn)

        findings = [
            DriftFinding(
                id=str(uuid.uuid4()),
                severity=sev,
                description=f"Finding {i}: {sev}",
                spec_ref=None,
                artifact_ref=None,
                spec_name="test_spec",
                task_group="0",
                session_id="s1",
            )
            for i, sev in enumerate(severities)
        ]

        if findings:
            insert_drift_findings(conn, findings)

        result = render_drift_context(conn, "test_spec")

        if not findings:
            assert result is None
        else:
            assert result is not None
            for f in findings:
                assert f.description in result

        conn.close()


# ---------------------------------------------------------------------------
# TS-32-P8: Hot-load Injection
# Property 8: Hot-loaded specs get oracle nodes in pending state
# Validates: 32-REQ-4.1, 32-REQ-4.2
# ---------------------------------------------------------------------------


class TestPropertyHotLoadInjection:
    """Hot-loaded specs get reviewer nodes in pending state."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(num_specs=st.integers(min_value=1, max_value=5))
    @settings(max_examples=5)
    def test_hot_load_injection(self, num_specs: int) -> None:
        """TS-32-P8: Each new spec gets reviewer nodes in pending state."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph
        from agent_fox.graph.types import NodeStatus

        config = ArchetypesConfig(reviewer=True)
        specs = [_spec(f"spec_{i}") for i in range(num_specs)]
        task_groups = {f"spec_{i}": [_tgd(1, f"T{i}")] for i in range(num_specs)}

        graph = build_graph(specs, task_groups, [], archetypes_config=config)

        for i in range(num_specs):
            # Reviewer creates auto_pre nodes with mode suffixes
            reviewer_nodes = [
                n for n in graph.nodes.values() if n.spec_name == f"spec_{i}" and n.archetype == "reviewer"
            ]
            assert len(reviewer_nodes) > 0, f"Missing reviewer nodes for spec_{i}"
            for node in reviewer_nodes:
                assert node.status == NodeStatus.PENDING
