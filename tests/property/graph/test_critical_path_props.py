"""Property tests for critical path computation.

Test Spec: TS-43-P2 (determinism), TS-43-P5 (duration optimality)
Properties: Property 2 and Property 3 from design.md
Validates: 43-REQ-2.1, 43-REQ-2.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.graph.critical_path import compute_critical_path


@st.composite
def dag_strategy(
    draw: st.DrawFn,
) -> tuple[dict[str, str], dict[str, list[str]], dict[str, int]]:
    """Generate random DAGs with duration hints.

    Nodes are named n0..n(N-1). Edges only go from lower to higher IDs
    to guarantee acyclicity.
    """
    n = draw(st.integers(min_value=0, max_value=12))
    node_ids = [f"n{i}" for i in range(n)]
    nodes = {nid: "pending" for nid in node_ids}

    edges: dict[str, list[str]] = {}
    for i, nid in enumerate(node_ids):
        # Each node can depend on any subset of earlier nodes
        possible_preds = node_ids[:i]
        if possible_preds:
            preds = draw(
                st.lists(
                    st.sampled_from(possible_preds),
                    max_size=min(3, len(possible_preds)),
                    unique=True,
                )
            )
        else:
            preds = []
        edges[nid] = preds

    durations = {
        nid: draw(st.integers(min_value=0, max_value=1000)) for nid in node_ids
    }

    return nodes, edges, durations


def _forward_pass(
    nodes: dict[str, str],
    edges: dict[str, list[str]],
    durations: dict[str, int],
) -> dict[str, int]:
    """Independently compute earliest finish times for verification."""
    if not nodes:
        return {}

    node_ids = list(nodes.keys())
    # Build successor map and in-degree
    successors: dict[str, list[str]] = {n: [] for n in node_ids}
    in_degree: dict[str, int] = {n: 0 for n in node_ids}

    for node, preds in edges.items():
        if node not in nodes:
            continue
        for pred in preds:
            if pred in successors:
                successors[pred].append(node)
            in_degree[node] = in_degree.get(node, 0) + 1

    # Topological sort
    from collections import deque

    queue: deque[str] = deque()
    for n in sorted(node_ids):
        if in_degree.get(n, 0) == 0:
            queue.append(n)

    topo_order: list[str] = []
    while queue:
        n = queue.popleft()
        topo_order.append(n)
        for succ in sorted(successors[n]):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    # Forward pass
    ef: dict[str, int] = {}
    for n in topo_order:
        dur = durations.get(n, 0)
        preds = edges.get(n, [])
        max_pred = max((ef.get(p, 0) for p in preds), default=0)
        ef[n] = max_pred + dur

    return ef


class TestCriticalPathDeterminism:
    """TS-43-P2: Same inputs always produce same critical path.

    Property: Property 3 from design.md
    Validates: 43-REQ-2.1, 43-REQ-2.3
    """

    @given(dag=dag_strategy())
    @settings(max_examples=100, deadline=2000)
    def test_deterministic(
        self,
        dag: tuple[dict[str, str], dict[str, list[str]], dict[str, int]],
    ) -> None:
        """Two calls with identical inputs yield identical results."""
        nodes, edges, durations = dag
        r1 = compute_critical_path(nodes, edges, durations)
        r2 = compute_critical_path(nodes, edges, durations)
        assert r1.path == r2.path
        assert r1.total_duration_ms == r2.total_duration_ms
        assert r1.tied_paths == r2.tied_paths


class TestCriticalPathOptimality:
    """TS-43-P5: Critical path duration equals max earliest finish.

    Property: Property 2 from design.md
    Validates: 43-REQ-2.1
    """

    @given(dag=dag_strategy())
    @settings(max_examples=100, deadline=2000)
    def test_duration_equals_max_ef(
        self,
        dag: tuple[dict[str, str], dict[str, list[str]], dict[str, int]],
    ) -> None:
        """total_duration_ms equals independently computed max earliest finish."""
        nodes, edges, durations = dag
        result = compute_critical_path(nodes, edges, durations)
        ef = _forward_pass(nodes, edges, durations)
        expected_max = max(ef.values(), default=0)
        assert result.total_duration_ms == expected_max
