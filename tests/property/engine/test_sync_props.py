"""Property tests for graph sync: cascade completeness, ready task correctness.

Test Spec: TS-04-P1 (cascade completeness), TS-04-P2 (ready task correctness)
Properties: Property 2 (cascade completeness), Property 5 (ready task correctness)
Requirements: 04-REQ-1.1, 04-REQ-3.1, 04-REQ-10.1, 04-REQ-10.2
"""

from __future__ import annotations

from collections import deque

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.engine.sync import GraphSync

# -- Hypothesis strategies for generating DAGs --------------------------------


@st.composite
def random_dags(draw: st.DrawFn) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Generate a random DAG with 2-20 nodes.

    Returns (node_states, edges) where:
    - node_states maps node_id -> "pending"
    - edges maps node_id -> list of dependency node_ids

    Edges only go from lower to higher IDs, guaranteeing acyclicity.
    """
    n = draw(st.integers(min_value=2, max_value=20))

    node_ids = [f"N{i}" for i in range(1, n + 1)]
    node_states = {nid: "pending" for nid in node_ids}

    edges: dict[str, list[str]] = {}
    for i in range(1, n + 1):
        deps: list[str] = []
        for j in range(1, i):
            if draw(st.booleans()):
                deps.append(f"N{j}")
        if deps:
            edges[f"N{i}"] = deps

    return node_states, edges


@st.composite
def random_dag_with_completed_set(
    draw: st.DrawFn,
) -> tuple[dict[str, str], dict[str, list[str]], set[str]]:
    """Generate a DAG with a random valid completed-set.

    Only marks a node as completed if all its dependencies are also
    completed, ensuring the state is consistent.
    """
    node_states, edges = draw(random_dags())
    node_ids = list(node_states.keys())

    # Build a valid completed set by selecting nodes in dependency order
    completed: set[str] = set()
    for nid in node_ids:
        deps = edges.get(nid, [])
        if all(d in completed for d in deps):
            if draw(st.booleans()):
                completed.add(nid)

    return node_states, edges, completed


# -- Helpers -----------------------------------------------------------------


def bfs_forward(
    start: str,
    edges: dict[str, list[str]],
    all_nodes: set[str],
) -> set[str]:
    """Find all nodes transitively dependent on `start` (forward BFS).

    Given edges mapping node -> its dependencies, we need to find
    nodes that depend on `start` (reverse direction).
    """
    # Build reverse adjacency: node -> list of nodes that depend on it
    reverse: dict[str, list[str]] = {n: [] for n in all_nodes}
    for node, deps in edges.items():
        for dep in deps:
            reverse[dep].append(node)

    # BFS from start through reverse edges
    visited: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for dependent in reverse.get(current, []):
            if dependent not in visited:
                visited.add(dependent)
                queue.append(dependent)

    return visited


# -- Property tests ----------------------------------------------------------


class TestCascadeCompleteness:
    """TS-04-P1: Cascade completeness.

    For any DAG and any blocked node, all transitively dependent nodes
    are also blocked.

    Property 2 from design.md.
    """

    @given(data=random_dags())
    @settings(max_examples=100)
    def test_all_dependents_blocked(
        self,
        data: tuple[dict[str, str], dict[str, list[str]]],
    ) -> None:
        """After blocking a node, all its transitive dependents are blocked."""
        node_states, edges = data
        all_nodes = set(node_states.keys())

        if not all_nodes:
            return

        # Pick a random node to block
        blocked_node = min(all_nodes)  # Deterministic for reproducibility

        # Mark ancestors as completed so the blocked node is valid
        sync = GraphSync(dict(node_states), dict(edges))

        # Mark all ancestors of the blocked node as completed
        deps = edges.get(blocked_node, [])
        for dep in deps:
            sync.mark_completed(dep)

        sync.mark_blocked(blocked_node, "test failure")

        # All transitively dependent nodes must be blocked
        reachable = bfs_forward(blocked_node, edges, all_nodes)
        for node in reachable:
            assert sync.node_states[node] == "blocked", (
                f"Node {node} reachable from {blocked_node} "
                f"should be blocked but is {sync.node_states[node]}"
            )


class TestReadyTaskCorrectness:
    """TS-04-P2: Ready task correctness.

    For any graph state, every task reported as ready has all
    dependencies completed.

    Property 5 from design.md.
    """

    @given(data=random_dag_with_completed_set())
    @settings(max_examples=100)
    def test_ready_tasks_have_completed_deps(
        self,
        data: tuple[dict[str, str], dict[str, list[str]], set[str]],
    ) -> None:
        """Every ready task has all dependencies in completed status."""
        node_states, edges, completed_set = data

        sync = GraphSync(dict(node_states), dict(edges))
        for nid in completed_set:
            sync.mark_completed(nid)

        ready = sync.ready_tasks()
        for ready_node in ready:
            deps = edges.get(ready_node, [])
            for dep in deps:
                assert sync.node_states[dep] == "completed", (
                    f"Ready task {ready_node} has dependency {dep} "
                    f"in state {sync.node_states[dep]}, expected completed"
                )

    @given(data=random_dag_with_completed_set())
    @settings(max_examples=100)
    def test_ready_tasks_are_pending(
        self,
        data: tuple[dict[str, str], dict[str, list[str]], set[str]],
    ) -> None:
        """Every ready task is in pending status."""
        node_states, edges, completed_set = data

        sync = GraphSync(dict(node_states), dict(edges))
        for nid in completed_set:
            sync.mark_completed(nid)

        ready = sync.ready_tasks()
        for ready_node in ready:
            assert sync.node_states[ready_node] == "pending", (
                f"Ready task {ready_node} should be pending but is "
                f"{sync.node_states[ready_node]}"
            )


class TestBatchIndependence:
    """TS-04-P3: Batch independence for parallel dispatch.

    For any graph state, no task in the ready set depends on another task
    in the same ready set. This guarantees that all ready tasks can be
    safely dispatched in parallel without ordering constraints.

    This is a structural invariant of ``ready_tasks()`` — if task A is
    ready, all its dependencies are completed (not pending), so no other
    pending (and therefore ready) task is a dependency of A.
    """

    @given(data=random_dag_with_completed_set())
    @settings(max_examples=100)
    def test_ready_tasks_are_pairwise_independent(
        self,
        data: tuple[dict[str, str], dict[str, list[str]], set[str]],
    ) -> None:
        """No ready task depends on another ready task."""
        node_states, edges, completed_set = data

        sync = GraphSync(dict(node_states), dict(edges))
        for nid in completed_set:
            sync.mark_completed(nid)

        ready = sync.ready_tasks()
        ready_set = set(ready)

        for ready_node in ready:
            deps = edges.get(ready_node, [])
            for dep in deps:
                assert dep not in ready_set, (
                    f"Ready task {ready_node} depends on {dep} which is "
                    f"also in the ready set — batch is not independent"
                )
