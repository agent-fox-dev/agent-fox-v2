"""Graph state propagation: ready detection, cascade blocking.

Requirements: 04-REQ-1.1, 04-REQ-3.1, 04-REQ-3.2, 04-REQ-10.1, 04-REQ-10.2
"""

from __future__ import annotations

from collections import Counter, deque


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

    def ready_tasks(self) -> list[str]:
        """Return node_ids of all tasks that are ready to execute.

        A task is ready when:
        - Its status is ``pending``
        - All of its dependencies have status ``completed``

        Returns:
            List of ready node_ids, sorted alphabetically for
            deterministic ordering.
        """
        ready: list[str] = []
        for node_id, status in self.node_states.items():
            if status != "pending":
                continue
            deps = self._edges.get(node_id, [])
            if all(self.node_states.get(d) == "completed" for d in deps):
                ready.append(node_id)
        return sorted(ready)

    def mark_completed(self, node_id: str) -> None:
        """Mark a task as completed."""
        self.node_states[node_id] = "completed"

    def mark_failed(self, node_id: str) -> None:
        """Mark a task as failed (before retry decision)."""
        self.node_states[node_id] = "failed"

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
                # Only cascade to nodes that are not already completed
                if self.node_states.get(dependent) in ("completed",):
                    continue
                visited.add(dependent)
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

    def summary(self) -> dict[str, int]:
        """Return counts by status: {pending: N, completed: N, ...}."""
        return dict(Counter(self.node_states.values()))
