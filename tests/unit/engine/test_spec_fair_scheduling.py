"""Tests for spec-fair round-robin task scheduling.

Test Spec: TS-69-1 through TS-69-10, TS-69-E1 through TS-69-E4
Requirements: 69-REQ-1.1 through 69-REQ-3.E1
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TS-69-1 through TS-69-7: _interleave_by_spec()
# ---------------------------------------------------------------------------


class TestInterleaveBySpec:
    """Tests for the _interleave_by_spec() helper function.

    Test Spec: TS-69-1, TS-69-2, TS-69-3, TS-69-4, TS-69-5, TS-69-6, TS-69-7
    """

    def test_multi_spec_round_robin_ordering(self) -> None:
        """TS-69-1: Tasks from multiple specs are interleaved round-robin.

        Requirements: 69-REQ-1.1
        """
        from agent_fox.engine.graph_sync import _interleave_by_spec

        result = _interleave_by_spec(["65_foo:1", "67_bar:1", "67_bar:2", "68_baz:1"])
        assert result == ["65_foo:1", "67_bar:1", "68_baz:1", "67_bar:2"]

    def test_spec_number_ascending_order(self) -> None:
        """TS-69-2: Spec groups are ordered by numeric prefix ascending.

        Requirements: 69-REQ-1.2
        """
        from agent_fox.engine.graph_sync import _interleave_by_spec

        result = _interleave_by_spec(["68_later:1", "65_earlier:1"])
        assert result == ["65_earlier:1", "68_later:1"]

    def test_single_spec_alphabetical(self) -> None:
        """TS-69-3: Single-spec ready tasks are sorted alphabetically.

        Requirements: 69-REQ-1.3
        """
        from agent_fox.engine.graph_sync import _interleave_by_spec

        result = _interleave_by_spec(["42_spec:3", "42_spec:1", "42_spec:2"])
        assert result == ["42_spec:1", "42_spec:2", "42_spec:3"]

    def test_non_numeric_spec_prefix_sorts_last(self) -> None:
        """TS-69-4: Specs without numeric prefixes sort after numbered specs.

        Requirements: 69-REQ-1.4
        """
        from agent_fox.engine.graph_sync import _interleave_by_spec

        result = _interleave_by_spec(["no_number:1", "05_numbered:1"])
        assert result == ["05_numbered:1", "no_number:1"]

    def test_duration_hints_within_spec_group(self) -> None:
        """TS-69-5: Duration hints order tasks within spec group by duration descending.

        Requirements: 69-REQ-2.1
        """
        from agent_fox.engine.graph_sync import _interleave_by_spec

        result = _interleave_by_spec(
            ["42_spec:1", "42_spec:2", "42_spec:3"],
            duration_hints={"42_spec:1": 100, "42_spec:2": 500, "42_spec:3": 300},
        )
        assert result == ["42_spec:2", "42_spec:3", "42_spec:1"]

    def test_duration_hints_do_not_override_cross_spec_fairness(self) -> None:
        """TS-69-6: Duration hints do not override cross-spec round-robin ordering.

        Requirements: 69-REQ-2.2
        """
        from agent_fox.engine.graph_sync import _interleave_by_spec

        result = _interleave_by_spec(
            ["10_fast:1", "20_slow:1"],
            duration_hints={"10_fast:1": 100, "20_slow:1": 99999},
        )
        assert result[0] == "10_fast:1"
        assert result[1] == "20_slow:1"

    def test_duration_hints_partial_coverage_within_spec(self) -> None:
        """TS-69-7: Hinted tasks come before unhinted tasks within a spec group.

        Requirements: 69-REQ-2.3
        """
        from agent_fox.engine.graph_sync import _interleave_by_spec

        result = _interleave_by_spec(
            ["42_spec:1", "42_spec:2", "42_spec:3"],
            duration_hints={"42_spec:1": 200, "42_spec:3": 500},
        )
        assert result == ["42_spec:3", "42_spec:1", "42_spec:2"]


# ---------------------------------------------------------------------------
# TS-69-8, TS-69-9: _spec_name()
# ---------------------------------------------------------------------------


class TestSpecNameExtraction:
    """Tests for the _spec_name() helper function.

    Test Spec: TS-69-8, TS-69-9
    """

    def test_spec_name_extraction_simple(self) -> None:
        """TS-69-8: Spec name is extracted as everything before the first colon.

        Requirements: 69-REQ-3.1
        """
        from agent_fox.engine.graph_sync import _spec_name

        assert _spec_name("67_quality_gate:2") == "67_quality_gate"

    def test_spec_name_extraction_multi_colon(self) -> None:
        """TS-69-9: Only the first colon is used for splitting.

        Requirements: 69-REQ-3.2
        """
        from agent_fox.engine.graph_sync import _spec_name

        assert _spec_name("67_quality_gate:1:auditor") == "67_quality_gate"


# ---------------------------------------------------------------------------
# TS-69-10: GraphSync.ready_tasks() integration
# ---------------------------------------------------------------------------


class TestReadyTasksIntegration:
    """Integration tests for GraphSync.ready_tasks() with spec-fair ordering.

    Test Spec: TS-69-10
    """

    def test_ready_tasks_multi_spec_graph(self) -> None:
        """TS-69-10: ready_tasks() returns spec-fair ordering for multi-spec graph.

        Requirements: 69-REQ-1.1, 69-REQ-2.2
        """
        from agent_fox.engine.graph_sync import GraphSync

        gs = GraphSync({"67_qg:0": "pending", "68_cfg:0": "pending"}, {})
        result = gs.ready_tasks()
        assert result == ["67_qg:0", "68_cfg:0"]


# ---------------------------------------------------------------------------
# TS-69-E1 through TS-69-E4: Edge cases
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Pre-review priority scheduling (fixes #476)
# ---------------------------------------------------------------------------


class TestPreReviewPriority:
    """Tests for pre-review prioritization in _interleave_by_spec.

    Pre-review nodes (auto_pre at group 0) are placed before coder nodes
    in the ready queue so that blockers surface early.
    """

    def test_pre_reviews_before_coder_nodes(self) -> None:
        """Auto_pre review nodes appear before coder nodes."""
        from agent_fox.engine.graph_sync import _interleave_by_spec

        ready = [
            "65_foo:1",
            "65_foo:0:reviewer:pre-review",
            "67_bar:1",
            "67_bar:0:reviewer:pre-review",
        ]
        result = _interleave_by_spec(ready)
        pre_reviews = [n for n in result if ":0:" in n]
        coders = [n for n in result if ":0:" not in n]
        assert result == pre_reviews + coders

    def test_pre_review_fan_out_ordering(self) -> None:
        """High-fan-out specs' pre-reviews come first."""
        from agent_fox.engine.graph_sync import _interleave_by_spec

        ready = [
            "01_setup:0:reviewer:pre-review",
            "02_broker:0:reviewer:pre-review",
            "03_api:0:reviewer:pre-review",
        ]
        fan_out = {"02_broker": 4, "01_setup": 1, "03_api": 2}
        result = _interleave_by_spec(ready, fan_out_weights=fan_out)
        assert result[0] == "02_broker:0:reviewer:pre-review"
        assert result[1] == "03_api:0:reviewer:pre-review"
        assert result[2] == "01_setup:0:reviewer:pre-review"

    def test_fan_out_tie_breaks_by_spec_number(self) -> None:
        """Equal fan-out ties are broken by spec number ascending."""
        from agent_fox.engine.graph_sync import _interleave_by_spec

        ready = [
            "03_api:0:reviewer:pre-review",
            "01_setup:0:reviewer:pre-review",
        ]
        fan_out = {"01_setup": 2, "03_api": 2}
        result = _interleave_by_spec(ready, fan_out_weights=fan_out)
        assert result == [
            "01_setup:0:reviewer:pre-review",
            "03_api:0:reviewer:pre-review",
        ]

    def test_mixed_pre_review_and_coder_ordering(self) -> None:
        """Pre-reviews from all specs come before any coder node."""
        from agent_fox.engine.graph_sync import _interleave_by_spec

        ready = [
            "01_setup:1",
            "02_broker:0:reviewer:pre-review",
            "03_api:0:reviewer:pre-review",
            "01_setup:2",
        ]
        result = _interleave_by_spec(ready)
        # Pre-reviews first (round-robin: 02, 03)
        assert result[:2] == [
            "02_broker:0:reviewer:pre-review",
            "03_api:0:reviewer:pre-review",
        ]
        # Then coder nodes (round-robin: 01:1, 01:2)
        assert result[2:] == ["01_setup:1", "01_setup:2"]

    def test_drift_review_also_prioritized(self) -> None:
        """Drift-review (also auto_pre at group 0) is prioritized with pre-reviews."""
        from agent_fox.engine.graph_sync import _interleave_by_spec

        ready = [
            "01_setup:1",
            "02_broker:0:reviewer:drift-review",
            "02_broker:0:reviewer:pre-review",
        ]
        result = _interleave_by_spec(ready)
        assert result[0].startswith("02_broker:0:")
        assert result[1].startswith("02_broker:0:")
        assert result[2] == "01_setup:1"

    def test_single_auto_pre_node_id_format(self) -> None:
        """Single auto_pre with 'spec:0' format is also prioritized."""
        from agent_fox.engine.graph_sync import _interleave_by_spec

        ready = ["01_setup:1", "02_broker:0", "03_api:1"]
        result = _interleave_by_spec(ready)
        assert result[0] == "02_broker:0"


class TestIsAutoPre:
    """Tests for the _is_auto_pre() helper."""

    def test_suffixed_pre_review(self) -> None:
        from agent_fox.engine.graph_sync import _is_auto_pre

        assert _is_auto_pre("02_broker:0:reviewer:pre-review") is True

    def test_suffixed_drift_review(self) -> None:
        from agent_fox.engine.graph_sync import _is_auto_pre

        assert _is_auto_pre("02_broker:0:reviewer:drift-review") is True

    def test_single_auto_pre(self) -> None:
        from agent_fox.engine.graph_sync import _is_auto_pre

        assert _is_auto_pre("02_broker:0") is True

    def test_coder_group(self) -> None:
        from agent_fox.engine.graph_sync import _is_auto_pre

        assert _is_auto_pre("02_broker:1") is False

    def test_audit_review(self) -> None:
        from agent_fox.engine.graph_sync import _is_auto_pre

        assert _is_auto_pre("02_broker:3:reviewer:audit-review") is False

    def test_no_colon(self) -> None:
        from agent_fox.engine.graph_sync import _is_auto_pre

        assert _is_auto_pre("orphan_node") is False


class TestSpecFanOut:
    """Tests for GraphSync._compute_spec_fan_out()."""

    def test_fan_out_with_cross_spec_edges(self) -> None:
        """Specs with cross-spec dependents have non-zero fan-out."""
        from agent_fox.engine.graph_sync import GraphSync

        states = {
            "01_setup:1": "pending",
            "01_setup:2": "pending",
            "02_broker:1": "pending",
            "03_api:1": "pending",
        }
        edges = {
            "01_setup:1": [],
            "01_setup:2": ["01_setup:1"],
            "02_broker:1": ["01_setup:2"],
            "03_api:1": ["01_setup:2"],
        }
        gs = GraphSync(states, edges)
        fan_out = gs._compute_spec_fan_out()
        assert fan_out["01_setup"] == 2  # 02_broker and 03_api depend on it

    def test_fan_out_no_cross_spec(self) -> None:
        """No cross-spec edges means empty fan-out."""
        from agent_fox.engine.graph_sync import GraphSync

        states = {"01_a:1": "pending", "01_a:2": "pending"}
        edges = {"01_a:1": [], "01_a:2": ["01_a:1"]}
        gs = GraphSync(states, edges)
        fan_out = gs._compute_spec_fan_out()
        assert fan_out == {}

    def test_fan_out_counts_distinct_specs(self) -> None:
        """Multiple edges to same spec count as 1."""
        from agent_fox.engine.graph_sync import GraphSync

        states = {
            "01_a:1": "pending",
            "01_a:2": "pending",
            "02_b:1": "pending",
            "02_b:2": "pending",
        }
        edges = {
            "01_a:1": [],
            "01_a:2": ["01_a:1"],
            "02_b:1": ["01_a:1"],
            "02_b:2": ["01_a:2"],
        }
        gs = GraphSync(states, edges)
        fan_out = gs._compute_spec_fan_out()
        assert fan_out["01_a"] == 1  # only 02_b, counted once


class TestReadyTasksPreReviewIntegration:
    """Integration tests for ready_tasks() with pre-review priority."""

    def test_pre_reviews_ordered_first(self) -> None:
        """Pre-review nodes appear before coder nodes in ready_tasks()."""
        from agent_fox.engine.graph_sync import GraphSync

        states = {
            "01_setup:0:reviewer:pre-review": "pending",
            "01_setup:1": "pending",
            "02_broker:0:reviewer:pre-review": "pending",
            "02_broker:1": "pending",
        }
        edges = {
            "01_setup:0:reviewer:pre-review": [],
            "01_setup:1": ["01_setup:0:reviewer:pre-review"],
            "02_broker:0:reviewer:pre-review": [],
            "02_broker:1": ["02_broker:0:reviewer:pre-review"],
        }
        gs = GraphSync(states, edges)
        result = gs.ready_tasks()
        # Only pre-reviews are ready (coders depend on them)
        assert result == [
            "01_setup:0:reviewer:pre-review",
            "02_broker:0:reviewer:pre-review",
        ]

    def test_fan_out_affects_pre_review_order(self) -> None:
        """High-fan-out specs' pre-reviews ordered first in ready_tasks()."""
        from agent_fox.engine.graph_sync import GraphSync

        states = {
            "01_setup:0:reviewer:pre-review": "pending",
            "01_setup:1": "pending",
            "02_broker:0:reviewer:pre-review": "pending",
            "02_broker:1": "pending",
            "03_api:0:reviewer:pre-review": "pending",
            "03_api:1": "pending",
        }
        edges = {
            "01_setup:0:reviewer:pre-review": [],
            "01_setup:1": ["01_setup:0:reviewer:pre-review"],
            "02_broker:0:reviewer:pre-review": [],
            "02_broker:1": ["02_broker:0:reviewer:pre-review", "01_setup:1"],
            "03_api:0:reviewer:pre-review": [],
            "03_api:1": ["03_api:0:reviewer:pre-review", "01_setup:1"],
        }
        gs = GraphSync(states, edges)
        result = gs.ready_tasks()
        # 01_setup has fan-out 2 (02_broker and 03_api depend on it)
        # Pre-reviews: 01 first (highest fan-out), then 02, then 03
        assert result[0] == "01_setup:0:reviewer:pre-review"


# ---------------------------------------------------------------------------
# TS-69-E1 through TS-69-E4: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for spec-fair scheduling.

    Test Spec: TS-69-E1, TS-69-E2, TS-69-E3, TS-69-E4
    """

    def test_single_spec_identity(self) -> None:
        """TS-69-E1: Single-spec result equals sorted(input).

        Requirements: 69-REQ-1.E1
        """
        from agent_fox.engine.graph_sync import _interleave_by_spec

        ready = ["42_spec:3", "42_spec:1", "42_spec:0"]
        result = _interleave_by_spec(ready)
        assert result == sorted(ready)

    def test_empty_list(self) -> None:
        """TS-69-E2: Empty input returns empty output.

        Requirements: 69-REQ-1.E2
        """
        from agent_fox.engine.graph_sync import _interleave_by_spec

        assert _interleave_by_spec([]) == []

    def test_duration_hints_single_spec(self) -> None:
        """TS-69-E3: Duration ordering within a single spec.

        Requirements: 69-REQ-2.E1
        """
        from agent_fox.engine.graph_sync import _interleave_by_spec

        result = _interleave_by_spec(
            ["42_spec:1", "42_spec:2"],
            duration_hints={"42_spec:1": 100, "42_spec:2": 500},
        )
        assert result == ["42_spec:2", "42_spec:1"]

    def test_no_colon_node_id(self) -> None:
        """TS-69-E4: Node ID with no colon uses full ID as spec name.

        Requirements: 69-REQ-3.E1
        """
        from agent_fox.engine.graph_sync import _spec_name

        assert _spec_name("orphan_node") == "orphan_node"
