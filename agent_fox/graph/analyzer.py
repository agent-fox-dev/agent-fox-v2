"""Plan analyzer: parallelism analysis, critical path, and float computation.

Requirements: 20-REQ-1.*, 20-REQ-2.*
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from agent_fox.graph.types import TaskGraph


@dataclass(frozen=True)
class NodeTiming:
    """Scheduling metadata for a single node."""

    node_id: str
    earliest_start: int
    latest_start: int
    float: int


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

    # Compute topological order via Kahn's algorithm if not provided
    node_ids = list(graph.nodes.keys())
    if graph.order:
        topo_order = list(graph.order)
    else:
        topo_order = _kahn_sort(node_ids, predecessors, successors)

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
            float=node_float,
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
    zero_float_nodes = {nid for nid, t in timings.items() if t.float == 0}
    critical_path = _trace_critical_path(
        zero_float_nodes, es, successors, topo_order
    )

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


def _kahn_sort(
    node_ids: list[str],
    predecessors: dict[str, list[str]],
    successors: dict[str, list[str]],
) -> list[str]:
    """Topological sort using Kahn's algorithm."""
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
    for nid in node_ids:
        for pred in predecessors.get(nid, []):
            if pred in in_degree:
                in_degree[nid] = in_degree.get(nid, 0)  # already init'd
    # Recount properly
    in_degree = {nid: len(predecessors.get(nid, [])) for nid in node_ids}

    queue = sorted(nid for nid, deg in in_degree.items() if deg == 0)
    result: list[str] = []
    while queue:
        nid = queue.pop(0)
        result.append(nid)
        for succ in sorted(successors.get(nid, [])):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)
    return result


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
    nodes_with_float = [
        (nid, t) for nid, t in analysis.timings.items() if t.float > 0
    ]

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
            spec_float.setdefault(spec, []).append(t.float)

        float_parts = []
        for spec, floats in sorted(spec_float.items()):
            float_parts.append(f"{spec} has {len(floats)} groups of float")
        lines.append(
            f"  Nodes with float: {len(nodes_with_float)} ({', '.join(float_parts)})"
        )

    return "\n".join(lines)
