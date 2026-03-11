"""Dependency resolver: topological sort with cycle detection.

Requirements: 02-REQ-4.1, 02-REQ-4.2, 02-REQ-3.E2
"""

from __future__ import annotations

import copy
import heapq
import logging
from collections import defaultdict
from dataclasses import dataclass

from agent_fox.core.errors import PlanError
from agent_fox.graph.types import Edge, NodeStatus, PlanMetadata, TaskGraph

logger = logging.getLogger(__name__)


def _sort_key(node_id: str) -> tuple[str, int]:
    """Extract sort key from a node ID for deterministic tie-breaking.

    Breaks ties by spec prefix (ascending), then group number (ascending).
    Node IDs have the format ``{spec_name}:{group_number}`` or
    ``{spec_name}:{group_number}:{role}``.
    """
    parts = node_id.split(":")
    spec_name = parts[0]
    group_number = int(parts[1]) if len(parts) > 1 else 0
    return (spec_name, group_number)


def resolve_order(graph: TaskGraph) -> list[str]:
    """Compute a topological ordering of the task graph.

    Uses Kahn's algorithm. Ties are broken by spec prefix (ascending)
    then group number (ascending) for deterministic output.

    Args:
        graph: TaskGraph with nodes and edges.

    Returns:
        List of node IDs in execution order.

    Raises:
        PlanError: If the graph contains a cycle, listing involved nodes.
    """
    if not graph.nodes:
        logger.warning("No task groups found; empty execution order.")
        return []

    # Build adjacency list and compute in-degrees
    in_degree: dict[str, int] = {node_id: 0 for node_id in graph.nodes}
    adjacency: dict[str, list[str]] = defaultdict(list)

    for edge in graph.edges:
        in_degree[edge.target] += 1
        adjacency[edge.source].append(edge.target)

    # Initialize min-heap with nodes that have zero in-degree
    # Heap entries are (sort_key, node_id) for deterministic tie-breaking
    heap: list[tuple[tuple[str, int], str]] = []
    for node_id in graph.nodes:
        if in_degree[node_id] == 0:
            heapq.heappush(heap, (_sort_key(node_id), node_id))

    order: list[str] = []

    while heap:
        _, node_id = heapq.heappop(heap)
        order.append(node_id)

        for successor in adjacency[node_id]:
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                heapq.heappush(heap, (_sort_key(successor), successor))

    # Cycle detection: if not all nodes are in the order, there's a cycle
    if len(order) != len(graph.nodes):
        cycle_nodes = [node_id for node_id in graph.nodes if node_id not in set(order)]
        raise PlanError(
            f"Dependency cycle detected involving nodes: "
            f"{', '.join(sorted(cycle_nodes))}"
        )

    return order


# ---------------------------------------------------------------------------
# Fast-mode filter (merged from fast_mode.py)
# ---------------------------------------------------------------------------


def apply_fast_mode(graph: TaskGraph) -> TaskGraph:
    """Remove optional nodes and rewire dependencies.

    For each optional node B with predecessors {A1, A2} and
    successors {C1, C2}, add edges A_i -> C_j for all combinations,
    then remove B and its edges. B's status is set to SKIPPED.

    Args:
        graph: The full task graph.

    Returns:
        A new TaskGraph with optional nodes removed and dependencies
        rewired. The skipped nodes are retained in the graph with
        SKIPPED status but excluded from the ordering.
    """
    # Deep copy nodes so we don't mutate the original graph
    new_nodes = {nid: copy.copy(node) for nid, node in graph.nodes.items()}

    # Identify optional nodes
    optional_ids = {nid for nid, node in new_nodes.items() if node.optional}

    # If no optional nodes, resolve order and return with fast_mode metadata
    if not optional_ids:
        new_graph = TaskGraph(
            nodes=new_nodes,
            edges=list(graph.edges),
            order=[],
            metadata=PlanMetadata(
                created_at=graph.metadata.created_at,
                fast_mode=True,
                filtered_spec=graph.metadata.filtered_spec,
                version=graph.metadata.version,
            ),
        )
        new_graph.order = resolve_order(new_graph)
        return new_graph

    # Collect existing edges as a set for rewiring
    new_edges: set[tuple[str, str, str]] = set()
    for edge in graph.edges:
        new_edges.add((edge.source, edge.target, edge.kind))

    # For each optional node, rewire dependencies and remove its edges
    for opt_id in optional_ids:
        # Find predecessors and successors of this optional node
        preds = [(s, t, k) for s, t, k in new_edges if t == opt_id]
        succs = [(s, t, k) for s, t, k in new_edges if s == opt_id]

        # Add rewired edges: each predecessor -> each successor
        for pred_s, _, _ in preds:
            for _, succ_t, _ in succs:
                new_edges.add((pred_s, succ_t, "intra_spec"))

        # Remove all edges involving this optional node
        new_edges = {(s, t, k) for s, t, k in new_edges if s != opt_id and t != opt_id}

        # Set the optional node's status to SKIPPED
        new_nodes[opt_id].status = NodeStatus.SKIPPED

    # Build edge objects from the remaining edge tuples
    edge_list = [Edge(source=s, target=t, kind=k) for s, t, k in new_edges]

    # Build the new graph; compute order using only non-optional nodes
    order_nodes = {
        nid: node for nid, node in new_nodes.items() if nid not in optional_ids
    }
    order_graph = TaskGraph(
        nodes=order_nodes,
        edges=edge_list,
        order=[],
        metadata=PlanMetadata(
            created_at=graph.metadata.created_at,
            fast_mode=True,
            filtered_spec=graph.metadata.filtered_spec,
            version=graph.metadata.version,
        ),
    )
    computed_order = resolve_order(order_graph)

    return TaskGraph(
        nodes=new_nodes,
        edges=edge_list,
        order=computed_order,
        metadata=order_graph.metadata,
    )


# ---------------------------------------------------------------------------
# Plan analyzer (merged from analyzer.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeTiming:
    """Scheduling metadata for a single node."""

    node_id: str
    earliest_start: int
    latest_start: int
    slack: int


@dataclass(frozen=True)
class Phase:
    """A set of nodes that can execute concurrently."""

    phase_number: int
    earliest_start: int
    node_ids: list[str]

    @property
    def worker_count(self) -> int:
        return len(self.node_ids)


@dataclass(frozen=True)
class PlanAnalysis:
    """Complete analysis result."""

    phases: list[Phase]
    critical_path: list[str]
    critical_path_length: int
    peak_parallelism: int
    total_nodes: int
    total_phases: int
    timings: dict[str, NodeTiming]
    has_alternative_critical_paths: bool


def analyze_plan(graph: TaskGraph) -> PlanAnalysis:
    """Compute parallelism phases, critical path, and float for all nodes.

    Algorithm:
    1. Forward pass: compute earliest_start for each node using
       topological order. ES(n) = max(ES(pred) + 1) for all predecessors;
       0 for source nodes.
    2. Determine makespan = max(ES) + 1.
    3. Backward pass: compute latest_start for each node.
       LS(n) = min(LS(succ) - 1) for all successors; ES(n) for sinks.
    4. Float = LS - ES. Nodes with float == 0 are on the critical path.
    5. Group nodes by ES to form phases.
    6. Trace the critical path by following zero-float nodes from source
       to sink.
    """
    # Handle empty graph
    if not graph.nodes:
        return PlanAnalysis(
            phases=[],
            critical_path=[],
            critical_path_length=0,
            peak_parallelism=0,
            total_nodes=0,
            total_phases=0,
            timings={},
            has_alternative_critical_paths=False,
        )

    # Build adjacency structures for efficient lookup
    predecessors: dict[str, list[str]] = defaultdict(list)
    successors: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        predecessors[edge.target].append(edge.source)
        successors[edge.source].append(edge.target)

    # Use pre-computed order or compute via resolver
    node_ids = list(graph.nodes.keys())
    if graph.order:
        topo_order = list(graph.order)
    else:
        topo_order = resolve_order(graph)

    # Forward pass: compute earliest start (ES)
    es: dict[str, int] = {}
    for nid in topo_order:
        preds = predecessors.get(nid, [])
        if not preds:
            es[nid] = 0
        else:
            es[nid] = max(es[p] + 1 for p in preds)

    # Makespan
    makespan = max(es.values()) + 1 if es else 0

    # Backward pass: compute latest start (LS)
    ls: dict[str, int] = {}
    for nid in reversed(topo_order):
        succs = successors.get(nid, [])
        if not succs:
            # Sink node: LS = makespan - 1 (same as max ES for sinks)
            ls[nid] = makespan - 1
        else:
            ls[nid] = min(ls[s] - 1 for s in succs)

    # Compute timings
    timings: dict[str, NodeTiming] = {}
    for nid in node_ids:
        node_float = ls[nid] - es[nid]
        timings[nid] = NodeTiming(
            node_id=nid,
            earliest_start=es[nid],
            latest_start=ls[nid],
            slack=node_float,
        )

    # Group nodes by ES to form phases
    es_groups: dict[int, list[str]] = defaultdict(list)
    for nid in topo_order:
        es_groups[es[nid]].append(nid)

    phases = []
    for i, es_val in enumerate(sorted(es_groups.keys())):
        phases.append(
            Phase(
                phase_number=i + 1,
                earliest_start=es_val,
                node_ids=es_groups[es_val],
            )
        )

    total_phases = len(phases)
    peak_parallelism = max(p.worker_count for p in phases) if phases else 0

    # Trace critical path: follow zero-float nodes from source to sink
    zero_float_nodes = {nid for nid, t in timings.items() if t.slack == 0}
    critical_path = _trace_critical_path(zero_float_nodes, es, successors, topo_order)

    # Detect alternative critical paths
    has_alternatives = _has_alternative_paths(
        zero_float_nodes, successors, critical_path, es
    )

    return PlanAnalysis(
        phases=phases,
        critical_path=critical_path,
        critical_path_length=len(critical_path),
        peak_parallelism=peak_parallelism,
        total_nodes=len(node_ids),
        total_phases=total_phases,
        timings=timings,
        has_alternative_critical_paths=has_alternatives,
    )


def _trace_critical_path(
    zero_float_nodes: set[str],
    es: dict[str, int],
    successors: dict[str, list[str]],
    topo_order: list[str],
) -> list[str]:
    """Trace a critical path through zero-float nodes.

    Start from a zero-float source (ES=0), follow zero-float successors
    in ES order until reaching a sink.
    """
    if not zero_float_nodes:
        return []

    # Find zero-float source (ES=0)
    sources = [nid for nid in zero_float_nodes if es[nid] == 0]
    if not sources:
        return []

    # Pick first source (deterministic)
    path = [sorted(sources)[0]]

    while True:
        current = path[-1]
        succs = successors.get(current, [])
        # Filter to zero-float successors
        zf_succs = [s for s in succs if s in zero_float_nodes]
        if not zf_succs:
            break
        # Pick successor with lowest ES (they should all have ES = current ES + 1)
        next_node = min(zf_succs, key=lambda s: (es[s], s))
        path.append(next_node)

    return path


def _has_alternative_paths(
    zero_float_nodes: set[str],
    successors: dict[str, list[str]],
    critical_path: list[str],
    es: dict[str, int],
) -> bool:
    """Check if there are alternative critical paths.

    True if any zero-float node has multiple zero-float successors
    (branching), or if there are zero-float nodes not on the
    representative critical path (parallel components, tied paths).
    """
    # Branching: a zero-float node has multiple zero-float successors
    for nid in zero_float_nodes:
        succs = successors.get(nid, [])
        zf_succs = [s for s in succs if s in zero_float_nodes]
        if len(zf_succs) > 1:
            return True

    # Zero-float nodes not on the representative path
    if zero_float_nodes != set(critical_path):
        return True

    return False


def format_analysis(analysis: PlanAnalysis, graph: TaskGraph) -> str:
    """Format the analysis result for terminal display.

    Requirements: 20-REQ-1.1, 20-REQ-1.3
    """
    if not analysis.phases:
        return "No tasks to analyze"

    lines: list[str] = []
    lines.append("Parallelism Analysis")
    lines.append("=" * 20)
    lines.append("")

    # Phase listing
    for phase in analysis.phases:
        wl = "worker" if phase.worker_count == 1 else "workers"
        lines.append(f"Phase {phase.phase_number} ({phase.worker_count} {wl}):")
        for nid in phase.node_ids:
            node = graph.nodes.get(nid)
            title = node.title if node else nid
            lines.append(f"  {nid} -- {title}")
        lines.append("")

    # Critical path
    lines.append(f"Critical Path ({analysis.critical_path_length} nodes):")
    lines.append("  " + " -> ".join(analysis.critical_path))
    if analysis.has_alternative_critical_paths:
        lines.append("  (alternative critical paths exist)")
    lines.append("")

    # Float summary
    nodes_with_float = [(nid, t) for nid, t in analysis.timings.items() if t.slack > 0]

    # Summary
    lines.append("Summary:")
    lines.append(f"  Phases:          {analysis.total_phases}")
    lines.append(f"  Peak workers:    {analysis.peak_parallelism}")
    lines.append(f"  Critical path:   {analysis.critical_path_length} nodes")
    lines.append(f"  Total nodes:     {analysis.total_nodes}")

    if nodes_with_float:
        # Group float by spec
        spec_float: dict[str, list[int]] = {}
        for nid, t in nodes_with_float:
            node = graph.nodes.get(nid)
            spec = node.spec_name if node else "unknown"
            spec_float.setdefault(spec, []).append(t.slack)

        float_parts = []
        for spec, floats in sorted(spec_float.items()):
            float_parts.append(f"{spec} has {len(floats)} groups of float")
        lines.append(
            f"  Nodes with float: {len(nodes_with_float)} ({', '.join(float_parts)})"
        )

    return "\n".join(lines)
