"""Graph state propagation: ready detection, cascade blocking.

Maintains a mutable view of node statuses and provides methods to
transition nodes through states, detect ready tasks, cascade-block
dependents, and detect stall conditions.
"""

from __future__ import annotations

from collections import Counter, deque


def _spec_name(node_id: str) -> str:
    """Extract spec name from node ID (everything before first colon).

    Requirements: 69-REQ-3.1, 69-REQ-3.2, 69-REQ-3.E1
    """
    idx = node_id.find(":")
    return node_id[:idx] if idx != -1 else node_id


def _spec_number(spec_name: str) -> tuple[int, str]:
    """Extract numeric prefix for sorting. Returns (number, name) tuple.

    Specs with numeric prefixes sort by number ascending.
    Specs without numeric prefixes sort after all numbered specs.

    Requirements: 69-REQ-1.2, 69-REQ-1.4
    """
    parts = spec_name.split("_", 1)
    try:
        return (int(parts[0]), spec_name)
    except (ValueError, IndexError):
        return (float("inf"), spec_name)  # type: ignore[return-value]


def _interleave_by_spec(
    ready: list[str],
    duration_hints: dict[str, int] | None = None,
) -> list[str]:
    """Order ready tasks with spec-fair round-robin interleaving.

    1. Group tasks by spec name (everything before first ':' in node ID).
    2. Sort spec groups by spec number ascending (numeric prefix).
    3. Within each group, sort by duration descending (if hints), else
       alphabetically. Hinted tasks come before unhinted tasks.
    4. Interleave across groups: take one from each spec per round.

    Args:
        ready: List of ready node IDs.
        duration_hints: Optional mapping of node_id -> predicted duration ms.

    Returns:
        Spec-fair-ordered list of node IDs.

    Requirements: 69-REQ-1.1, 69-REQ-1.3, 69-REQ-2.1, 69-REQ-2.2, 69-REQ-2.3
    """
    if not ready:
        return []

    # Group tasks by spec name
    groups: dict[str, list[str]] = {}
    for node_id in ready:
        spec = _spec_name(node_id)
        groups.setdefault(spec, []).append(node_id)

    # Sort spec groups by spec number ascending
    sorted_specs = sorted(groups.keys(), key=_spec_number)

    # Sort within each group
    sorted_groups: list[list[str]] = []
    for spec in sorted_specs:
        tasks = groups[spec]
        if duration_hints:
            hinted = [(t, duration_hints[t]) for t in tasks if t in duration_hints]
            unhinted = [t for t in tasks if t not in duration_hints]
            hinted.sort(key=lambda x: x[1], reverse=True)
            unhinted.sort()
            sorted_groups.append([t for t, _ in hinted] + unhinted)
        else:
            sorted_groups.append(sorted(tasks))

    # Round-robin interleave across groups
    result: list[str] = []
    queues = [list(g) for g in sorted_groups]
    while any(queues):
        for q in queues:
            if q:
                result.append(q.pop(0))

    return result


class GraphSync:
    """Graph state propagation: ready detection, cascade blocking.

    Maintains a mutable view of node statuses and provides methods to
    transition nodes through states, detect ready tasks, cascade-block
    dependents, and detect stall conditions.
    """

    def __init__(
        self,
        node_states: dict[str, str],
        edges: dict[str, list[str]],
    ) -> None:
        """Initialise graph sync with node states and dependency edges.

        Args:
            node_states: Mutable dict of node_id -> status string.
                This is a shared reference — the same dict object is
                held by ExecutionState.node_states, so mutations here
                are immediately visible to the orchestrator and vice
                versa.
            edges: Adjacency list where each key is a node_id and its
                value is a list of dependency node_ids (predecessors
                that must complete before this node can execute).
        """
        self.node_states = node_states
        self._edges = edges

        # Build reverse adjacency: node -> list of nodes that depend on it.
        # Used for cascade blocking (BFS forward through dependents).
        self._dependents: dict[str, list[str]] = {n: [] for n in node_states}
        for node, deps in edges.items():
            for dep in deps:
                if dep in self._dependents:
                    self._dependents[dep].append(node)

    def ready_tasks(
        self,
        duration_hints: dict[str, int] | None = None,
    ) -> list[str]:
        """Return node_ids of all tasks that are ready to execute.

        A task is ready when:
        - Its status is ``pending``
        - All of its dependencies have status ``completed``

        Args:
            duration_hints: Optional mapping of node_id to predicted
                duration in milliseconds. When provided, ready tasks are
                sorted by duration descending within each spec group.
                Cross-spec ordering uses spec-fair round-robin regardless
                of duration hints.

        Returns:
            List of ready node_ids in spec-fair round-robin order.
            Spec groups are ordered by numeric prefix ascending; within
            each spec group tasks are sorted alphabetically or by
            duration descending when hints are provided.

        Requirements: 39-REQ-1.1, 39-REQ-1.3, 69-REQ-1.1, 69-REQ-2.2
        """
        ready: list[str] = []
        for node_id, status in self.node_states.items():
            if status != "pending":
                continue
            deps = self._edges.get(node_id, [])
            if all(self.node_states.get(d) == "completed" for d in deps):
                ready.append(node_id)

        return _interleave_by_spec(ready, duration_hints)

    def predecessors(self, node_id: str) -> list[str]:
        """Return predecessor node IDs for *node_id*."""
        return self._edges.get(node_id, [])

    def mark_completed(self, node_id: str) -> None:
        """Mark a task as completed."""
        self.node_states[node_id] = "completed"

    def mark_blocked(self, node_id: str, reason: str) -> list[str]:
        """Mark a task as blocked and cascade-block all dependents.

        Uses BFS to find all transitively dependent nodes and marks
        them as blocked.

        Args:
            node_id: The task that exhausted retries.
            reason: Human-readable blocking reason.

        Returns:
            List of node_ids that were cascade-blocked (does not include
            the originally blocked node itself).
        """
        self.node_states[node_id] = "blocked"

        # BFS through dependents to cascade the block
        cascade_blocked: list[str] = []
        queue: deque[str] = deque([node_id])
        visited: set[str] = {node_id}

        while queue:
            current = queue.popleft()
            for dependent in self._dependents.get(current, []):
                if dependent in visited:
                    continue
                # Skip completed nodes — their work is done and cannot be
                # reversed.
                if self.node_states.get(dependent) == "completed":
                    continue
                visited.add(dependent)
                # In-progress nodes are actively executing and cannot be
                # forcibly terminated.  We do NOT mark them "blocked" here,
                # but we MUST continue the BFS through them so that their
                # pending dependents are blocked.  Without this traversal,
                # those dependents would appear in ready_tasks() when the
                # in-progress node completes and be dispatched despite the
                # quality gate (issue #481).
                if self.node_states.get(dependent) == "in_progress":
                    queue.append(dependent)
                    continue
                self.node_states[dependent] = "blocked"
                cascade_blocked.append(dependent)
                queue.append(dependent)

        return cascade_blocked

    def mark_in_progress(self, node_id: str) -> None:
        """Mark a task as in_progress (being executed)."""
        self.node_states[node_id] = "in_progress"

    def is_stalled(self) -> bool:
        """Check if no progress is possible.

        Returns True when no tasks are ready, no tasks are in_progress,
        but incomplete tasks remain (i.e. there are still pending or
        blocked tasks that are not completed).
        """
        has_ready = bool(self.ready_tasks())
        has_in_progress = any(s == "in_progress" for s in self.node_states.values())
        all_completed = all(s == "completed" for s in self.node_states.values())

        if has_ready or has_in_progress or all_completed:
            return False

        return True

    def completed_spec_names(self) -> set[str]:
        """Return the set of spec names where all nodes are completed.

        Groups node_states by spec name (the part before the first ':'
        in each node ID) and returns only those specs where every node
        has status ``"completed"``.

        Returns:
            Set of spec folder names (e.g. ``{"05_foo"}``) that are
            fully completed.

        Requirements: 92-REQ-4.1
        """
        # Group nodes by spec name
        spec_nodes: dict[str, list[str]] = {}
        for node_id in self.node_states:
            spec = _spec_name(node_id)
            spec_nodes.setdefault(spec, []).append(node_id)

        return {spec for spec, nodes in spec_nodes.items() if all(self.node_states[n] == "completed" for n in nodes)}

    def summary(self) -> dict[str, int]:
        """Return counts by status: {pending: N, completed: N, ...}."""
        return dict(Counter(self.node_states.values()))
