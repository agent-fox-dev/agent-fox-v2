# Requirements Document

## Introduction

This specification defines the `--dry-run` flag for the `agent-fox plan`
command. The flag runs the full planning pipeline without persisting to DuckDB
and displays a richer analysis including parallelism phases, dependency edges,
and the critical path.

## Glossary

- **Parallelism phase**: A maximal set of task graph nodes that can execute
  concurrently. Nodes in phase N have all predecessors in phases 0..N-1.
  Phase 0 contains all nodes with zero in-degree.
- **Critical path**: The longest dependency chain (by node count) from any
  source node (zero in-degree) to any sink node (zero out-degree) in the
  task graph DAG.
- **Topological depth**: The length of the longest path from any source node
  to a given node. Nodes at the same depth form a parallelism phase.
- **Task graph**: The directed acyclic graph of plan nodes and dependency
  edges produced by the planning pipeline.
- **DuckDB persistence**: The act of writing plan nodes, edges, and metadata
  to the DuckDB knowledge store via `save_plan()`.
- **Intra-spec edge**: A dependency edge between two nodes within the same
  specification (sequential task group ordering).
- **Cross-spec edge**: A dependency edge between nodes in different
  specifications (declared in `prd.md` dependency tables).
- **Source node**: A node with zero in-degree (no predecessors).
- **Sink node**: A node with zero out-degree (no successors).

## Requirements

### Requirement 1: Analyze Flag Skips Persistence

**User Story:** As a user, I want to preview the execution plan without
modifying the database, so that I can inspect the plan before committing it.

#### Acceptance Criteria

1. [122-REQ-1.1] WHEN the user runs `plan --dry-run`, THE system SHALL
   execute the full planning pipeline (discovery, parsing, building,
   resolving) AND return the resolved TaskGraph to the caller without
   invoking `save_plan()`.

2. [122-REQ-1.2] WHEN the user runs `plan` without `--dry-run`, THE system
   SHALL persist the plan to DuckDB as before (existing behavior unchanged).

3. [122-REQ-1.3] WHEN the user runs `plan --dry-run`, THE system SHALL
   exit with code 0 on success and code 1 on plan error.

#### Edge Cases

1. [122-REQ-1.E1] IF the specs directory is empty or contains no valid
   specs, THEN THE system SHALL display an appropriate error and exit with
   code 1 (same behavior as normal plan).

2. [122-REQ-1.E2] IF a dependency cycle is detected during `--dry-run`,
   THEN THE system SHALL report the cycle error and exit with code 1 (same
   behavior as normal plan).

### Requirement 2: Parallelism Phase Analysis

**User Story:** As a user, I want to see which tasks can run concurrently,
so that I can understand the degree of parallelism in the plan.

#### Acceptance Criteria

1. [122-REQ-2.1] WHEN `--dry-run` is set, THE system SHALL compute
   parallelism phases by grouping nodes by topological depth AND return
   the phases as an ordered list of (phase_number, list_of_node_ids) tuples
   to the caller.

2. [122-REQ-2.2] WHEN `--dry-run` is set, THE system SHALL display each
   phase with its phase number and the nodes it contains, showing node ID
   and title for each node.

3. [122-REQ-2.3] WHEN `--dry-run` is set, THE system SHALL display a
   summary line showing the total number of phases and the peak parallelism
   (the largest phase size).

#### Edge Cases

1. [122-REQ-2.E1] IF the plan contains a single node, THEN THE system
   SHALL display one phase containing that single node with peak
   parallelism of 1.

### Requirement 3: Dependency Edge Display

**User Story:** As a user, I want to see the explicit dependency edges
between tasks, so that I can understand why tasks are ordered the way they
are.

#### Acceptance Criteria

1. [122-REQ-3.1] WHEN `--dry-run` is set, THE system SHALL display all
   dependency edges grouped by type (intra-spec, cross-spec) AND return
   the grouped edges to the caller.

2. [122-REQ-3.2] WHEN `--dry-run` is set, THE system SHALL display each
   edge as `source_node_id -> target_node_id`.

#### Edge Cases

1. [122-REQ-3.E1] IF the plan contains no cross-spec edges, THEN THE
   system SHALL omit the cross-spec section entirely from the display.

### Requirement 4: Critical Path Analysis

**User Story:** As a user, I want to see the bottleneck dependency chain,
so that I can identify which tasks constrain the overall schedule.

#### Acceptance Criteria

1. [122-REQ-4.1] WHEN `--dry-run` is set, THE system SHALL compute the
   critical path as the longest path (by node count) from any source node
   to any sink node AND return the path as an ordered list of node IDs to
   the caller.

2. [122-REQ-4.2] WHEN `--dry-run` is set, THE system SHALL display the
   critical path as a chain of node IDs (`A -> B -> C`) with the total
   length.

3. [122-REQ-4.3] WHEN multiple paths of equal length exist, THE system
   SHALL select one deterministically using lexicographic ordering of
   node IDs at each tie-break point.

#### Edge Cases

1. [122-REQ-4.E1] IF the plan contains a single node, THEN THE system
   SHALL report a critical path of length 1 containing that single node.

2. [122-REQ-4.E2] IF the plan is empty (no nodes), THEN THE system SHALL
   report no critical path.

### Requirement 5: Flag Composability

**User Story:** As a user, I want `--dry-run` to work with `--fast`,
`--spec`, and `--json`, so that I can analyze filtered or fast-mode plans
and get machine-readable output.

#### Acceptance Criteria

1. [122-REQ-5.1] WHEN the user runs `plan --dry-run --fast`, THE system
   SHALL apply fast-mode filtering before computing the analysis AND
   display the analysis of the filtered plan.

2. [122-REQ-5.2] WHEN the user runs `plan --dry-run --spec NAME`, THE
   system SHALL restrict the plan to the named spec before computing the
   analysis.

3. [122-REQ-5.3] WHEN the user runs `plan --dry-run --json`, THE system
   SHALL output a JSON object containing keys `nodes`, `edges`, `order`,
   `metadata`, `phases`, `critical_path`, and `grouped_edges` AND return
   exit code 0.

4. [122-REQ-5.4] WHEN the user runs `plan --dry-run --fast --spec NAME
   --json`, THE system SHALL apply all flags and produce the combined
   JSON analysis output.

#### Edge Cases

1. [122-REQ-5.E1] IF `--dry-run --spec NAME` is used and the named spec
   does not exist, THEN THE system SHALL report an error and exit with
   code 1.

### Requirement 6: Programmatic API

**User Story:** As a developer, I want to call `run_plan()` with an
dry_run parameter, so that I can preview plans programmatically without
database side effects.

#### Acceptance Criteria

1. [122-REQ-6.1] WHEN `run_plan()` is called with `analyze=True`, THE
   system SHALL build the plan and return the TaskGraph without calling
   `save_plan()` or opening a database connection.

2. [122-REQ-6.2] WHEN `run_plan()` is called with `analyze=False` (the
   default), THE system SHALL persist the plan to DuckDB as before
   (existing behavior unchanged).
