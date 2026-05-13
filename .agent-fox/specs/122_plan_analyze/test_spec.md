# Test Specification: --dry-run Flag on plan Command

## Overview

Tests verify that the `--dry-run` flag runs the planning pipeline without
database persistence, computes correct parallelism phases, critical path,
and edge grouping, and renders output in both human-readable and JSON
formats. Test cases map 1:1 to requirements and correctness properties.

## Test Cases

### TS-122-1: Analyze flag skips persistence

**Requirement:** 122-REQ-1.1
**Type:** integration
**Description:** Verify that `plan --dry-run` does not call `save_plan()`.

**Preconditions:**
- A valid specs directory with at least one spec containing `tasks.md`.

**Input:**
- CLI invocation: `plan --dry-run`

**Expected:**
- `build_plan()` is called and returns a TaskGraph.
- `save_plan()` is NOT called.
- `open_knowledge_store()` is NOT called.
- Exit code 0.

**Assertion pseudocode:**
```
runner = CliRunner()
with patch("agent_fox.cli.plan.save_plan") as mock_save:
    with patch("agent_fox.cli.plan.open_knowledge_store") as mock_db:
        result = runner.invoke(plan_cmd, ["--dry-run"], obj={"json": False})
        ASSERT result.exit_code == 0
        ASSERT mock_save.call_count == 0
        ASSERT mock_db.call_count == 0
```

### TS-122-2: Normal plan still persists

**Requirement:** 122-REQ-1.2
**Type:** integration
**Description:** Verify that `plan` without `--dry-run` still calls `save_plan()`.

**Preconditions:**
- A valid specs directory with at least one spec.

**Input:**
- CLI invocation: `plan` (no --dry-run flag)

**Expected:**
- `save_plan()` IS called exactly once.
- Exit code 0.

**Assertion pseudocode:**
```
runner = CliRunner()
with patch("agent_fox.cli.plan.save_plan") as mock_save:
    result = runner.invoke(plan_cmd, [], obj={"json": False})
    ASSERT result.exit_code == 0
    ASSERT mock_save.call_count == 1
```

### TS-122-3: Analyze exit codes

**Requirement:** 122-REQ-1.3
**Type:** integration
**Description:** Verify correct exit codes for --dry-run mode.

**Preconditions:**
- Valid specs directory for success case.
- Invalid/empty specs directory for error case.

**Input:**
- Success: `plan --dry-run` with valid specs.
- Error: `plan --dry-run` with a spec containing a dependency cycle.

**Expected:**
- Success: exit code 0.
- Error: exit code 1.

**Assertion pseudocode:**
```
result_ok = runner.invoke(plan_cmd, ["--dry-run"], obj={"json": False})
ASSERT result_ok.exit_code == 0

with patch("agent_fox.graph.planner.build_plan", side_effect=PlanError("cycle")):
    result_err = runner.invoke(plan_cmd, ["--dry-run"], obj={"json": False})
    ASSERT result_err.exit_code == 1
```

### TS-122-4: Compute phases groups nodes by topological depth

**Requirement:** 122-REQ-2.1
**Type:** unit
**Description:** Verify `compute_phases()` assigns correct phase numbers.

**Preconditions:**
- A TaskGraph with nodes A, B, C, D and edges A→B, A→C, B→D, C→D
  (diamond shape).

**Input:**
- The diamond TaskGraph described above.

**Expected:**
- Phase 0: [A]
- Phase 1: [B, C] (sorted lexicographically)
- Phase 2: [D]

**Assertion pseudocode:**
```
graph = make_diamond_graph()
phases = compute_phases(graph)
ASSERT len(phases) == 3
ASSERT phases[0].node_ids == ["A"]
ASSERT phases[1].node_ids == ["B", "C"]
ASSERT phases[2].node_ids == ["D"]
```

### TS-122-5: Phases displayed with node IDs and titles

**Requirement:** 122-REQ-2.2
**Type:** unit
**Description:** Verify `format_plan_analysis()` includes phase headings
and node details.

**Preconditions:**
- A TaskGraph with known nodes and computed phases.

**Input:**
- Phases from a diamond graph.

**Expected:**
- Output contains "Phase 0", "Phase 1", "Phase 2".
- Each phase lists node IDs with their titles.

**Assertion pseudocode:**
```
output = format_plan_analysis(graph, phases, path, grouped, specs)
ASSERT "Phase 0" in output
ASSERT "Phase 1" in output
ASSERT "A" in output and "node_A_title" in output
```

### TS-122-6: Phase summary line

**Requirement:** 122-REQ-2.3
**Type:** unit
**Description:** Verify the summary line shows phase count and peak
parallelism.

**Preconditions:**
- Phases computed from a diamond graph (3 phases, peak=2).

**Input:**
- Diamond graph phases.

**Expected:**
- Output contains "3 phases, peak parallelism: 2".

**Assertion pseudocode:**
```
output = format_plan_analysis(graph, phases, path, grouped, specs)
ASSERT "3 phases" in output
ASSERT "peak parallelism: 2" in output
```

### TS-122-7: Edges grouped and displayed by type

**Requirement:** 122-REQ-3.1
**Type:** unit
**Description:** Verify `group_edges()` partitions edges by kind.

**Preconditions:**
- A TaskGraph with both intra-spec and cross-spec edges.

**Input:**
- Graph with 3 intra-spec edges and 1 cross-spec edge.

**Expected:**
- `grouped.intra_spec` has 3 edges.
- `grouped.cross_spec` has 1 edge.

**Assertion pseudocode:**
```
grouped = group_edges(graph)
ASSERT len(grouped.intra_spec) == 3
ASSERT len(grouped.cross_spec) == 1
```

### TS-122-8: Edge display format

**Requirement:** 122-REQ-3.2
**Type:** unit
**Description:** Verify edges are displayed as `source -> target`.

**Preconditions:**
- Grouped edges from a graph.

**Input:**
- Grouped edges with known source/target pairs.

**Expected:**
- Output contains "A -> B" for each edge.

**Assertion pseudocode:**
```
output = format_plan_analysis(graph, phases, path, grouped, specs)
ASSERT "A -> B" in output
```

### TS-122-9: Critical path computation

**Requirement:** 122-REQ-4.1
**Type:** unit
**Description:** Verify `critical_path()` finds the longest path.

**Preconditions:**
- A TaskGraph with a diamond shape: A→B→D (length 3) and A→C→D (length 3),
  plus an extra chain A→B→E→F (length 4).

**Input:**
- The graph described above.

**Expected:**
- Critical path: [A, B, E, F] (length 4).

**Assertion pseudocode:**
```
graph = make_graph_with_long_branch()
path = critical_path(graph)
ASSERT path == ["A", "B", "E", "F"]
ASSERT len(path) == 4
```

### TS-122-10: Critical path display

**Requirement:** 122-REQ-4.2
**Type:** unit
**Description:** Verify critical path is rendered as a chain.

**Preconditions:**
- Known critical path [A, B, C].

**Input:**
- Path [A, B, C].

**Expected:**
- Output contains "A -> B -> C" and "Length: 3 nodes".

**Assertion pseudocode:**
```
output = format_plan_analysis(graph, phases, ["A", "B", "C"], grouped, specs)
ASSERT "A -> B -> C" in output
ASSERT "Length: 3 nodes" in output
```

### TS-122-11: Critical path deterministic tie-break

**Requirement:** 122-REQ-4.3
**Type:** unit
**Description:** Verify deterministic selection when multiple equal-length
paths exist.

**Preconditions:**
- A diamond graph A→B→D and A→C→D where B < C lexicographically, both
  paths length 3.

**Input:**
- Diamond graph.

**Expected:**
- Critical path is [A, B, D] (B before C lexicographically).

**Assertion pseudocode:**
```
graph = make_diamond_graph()
path1 = critical_path(graph)
path2 = critical_path(graph)
ASSERT path1 == path2
ASSERT path1 == ["A", "B", "D"]
```

### TS-122-12: Analyze composable with --fast

**Requirement:** 122-REQ-5.1
**Type:** integration
**Description:** Verify `--dry-run --fast` applies fast-mode filtering
before analysis.

**Preconditions:**
- Specs with optional task groups.

**Input:**
- CLI invocation: `plan --dry-run --fast`

**Expected:**
- Analysis output reflects fast-mode filtering (optional nodes skipped).
- No database persistence.

**Assertion pseudocode:**
```
result = runner.invoke(plan_cmd, ["--dry-run", "--fast"], obj={"json": False})
ASSERT result.exit_code == 0
ASSERT "Fast mode:     on" in result.output
```

### TS-122-13: Analyze composable with --spec

**Requirement:** 122-REQ-5.2
**Type:** integration
**Description:** Verify `--dry-run --spec NAME` restricts analysis to one
spec.

**Preconditions:**
- Multiple specs in the specs directory.

**Input:**
- CLI invocation: `plan --dry-run --spec spec_a`

**Expected:**
- Analysis only includes nodes from spec_a.
- No database persistence.

**Assertion pseudocode:**
```
result = runner.invoke(plan_cmd, ["--dry-run", "--spec", "spec_a"], obj={"json": False})
ASSERT result.exit_code == 0
ASSERT "spec_a" in result.output
ASSERT "spec_b" not in result.output
```

### TS-122-14: Analyze with --json output

**Requirement:** 122-REQ-5.3
**Type:** integration
**Description:** Verify `--dry-run --json` produces structured JSON with
analysis keys.

**Preconditions:**
- Valid specs directory.

**Input:**
- CLI invocation: `plan --dry-run --json`

**Expected:**
- Output is valid JSON.
- JSON contains keys: `nodes`, `edges`, `order`, `metadata`, `phases`,
  `critical_path`, `grouped_edges`.

**Assertion pseudocode:**
```
result = runner.invoke(plan_cmd, ["--dry-run"], obj={"json": True})
data = json.loads(result.output)
ASSERT "phases" in data
ASSERT "critical_path" in data
ASSERT "grouped_edges" in data
ASSERT "nodes" in data
```

### TS-122-15: All flags combined

**Requirement:** 122-REQ-5.4
**Type:** integration
**Description:** Verify `--dry-run --fast --spec NAME --json` works together.

**Preconditions:**
- Valid specs directory with at least two specs, one with optional tasks.

**Input:**
- CLI invocation: `plan --dry-run --fast --spec spec_a --json`

**Expected:**
- Valid JSON output with analysis keys.
- Only spec_a nodes present.
- Optional nodes skipped.

**Assertion pseudocode:**
```
result = runner.invoke(plan_cmd, ["--dry-run", "--fast", "--spec", "spec_a"], obj={"json": True})
data = json.loads(result.output)
ASSERT "phases" in data
all_spec_names = {node["spec_name"] for node in data["nodes"].values()}
ASSERT all_spec_names == {"spec_a"}
```

### TS-122-16: run_plan dry_run=True skips persistence

**Requirement:** 122-REQ-6.1
**Type:** unit
**Description:** Verify `run_plan(dry_run=True)` does not open DB or call
save_plan.

**Preconditions:**
- Valid config and specs directory.

**Input:**
- `run_plan(config, dry_run=True, specs_dir=...)`

**Expected:**
- Returns a TaskGraph.
- `open_knowledge_store()` not called.
- `save_plan()` not called.

**Assertion pseudocode:**
```
with patch("agent_fox.graph.planner.save_plan") as mock_save:
    with patch("agent_fox.graph.planner.open_knowledge_store") as mock_db:
        graph = run_plan(config, dry_run=True, specs_dir=specs_dir)
        ASSERT isinstance(graph, TaskGraph)
        ASSERT mock_save.call_count == 0
        ASSERT mock_db.call_count == 0
```

### TS-122-17: run_plan dry_run=False still persists

**Requirement:** 122-REQ-6.2
**Type:** unit
**Description:** Verify `run_plan(dry_run=False)` persists as before.

**Preconditions:**
- Valid config and specs directory.

**Input:**
- `run_plan(config, dry_run=False, specs_dir=...)`

**Expected:**
- Returns a TaskGraph.
- `save_plan()` called exactly once.

**Assertion pseudocode:**
```
with patch("agent_fox.graph.planner.save_plan") as mock_save:
    graph = run_plan(config, dry_run=False, specs_dir=specs_dir)
    ASSERT isinstance(graph, TaskGraph)
    ASSERT mock_save.call_count == 1
```

## Edge Case Tests

### TS-122-E1: Empty specs directory with --dry-run

**Requirement:** 122-REQ-1.E1
**Type:** integration
**Description:** Verify error handling when specs directory is empty.

**Preconditions:**
- An empty specs directory.

**Input:**
- CLI invocation: `plan --dry-run --specs-dir /empty`

**Expected:**
- Error message displayed.
- Exit code 1.

**Assertion pseudocode:**
```
result = runner.invoke(plan_cmd, ["--dry-run", "--specs-dir", str(empty_dir)], obj={"json": False})
ASSERT result.exit_code == 1
```

### TS-122-E2: Cycle detected during --dry-run

**Requirement:** 122-REQ-1.E2
**Type:** integration
**Description:** Verify cycle error is reported during --dry-run.

**Preconditions:**
- Specs that produce a dependency cycle.

**Input:**
- CLI invocation: `plan --dry-run`

**Expected:**
- Error output mentions "cycle".
- Exit code 1.
- No database persistence.

**Assertion pseudocode:**
```
with patch("agent_fox.graph.planner.build_plan", side_effect=PlanError("Dependency cycle detected")):
    result = runner.invoke(plan_cmd, ["--dry-run"], obj={"json": False})
    ASSERT result.exit_code == 1
    ASSERT "cycle" in result.output.lower() or "cycle" in (result.stderr or "").lower()
```

### TS-122-E3: Single node graph phases

**Requirement:** 122-REQ-2.E1
**Type:** unit
**Description:** Verify single-node graph produces one phase.

**Preconditions:**
- TaskGraph with exactly one node and no edges.

**Input:**
- Single-node graph.

**Expected:**
- One phase with that node.

**Assertion pseudocode:**
```
graph = make_single_node_graph("A")
phases = compute_phases(graph)
ASSERT len(phases) == 1
ASSERT phases[0].node_ids == ["A"]
```

### TS-122-E4: No cross-spec edges omits section

**Requirement:** 122-REQ-3.E1
**Type:** unit
**Description:** Verify cross-spec section is omitted when no cross-spec
edges exist.

**Preconditions:**
- TaskGraph with only intra-spec edges.

**Input:**
- Graph with intra-spec edges only.

**Expected:**
- Output does not contain "Cross-spec".

**Assertion pseudocode:**
```
output = format_plan_analysis(graph, phases, path, grouped, specs)
ASSERT "Cross-spec" not in output
```

### TS-122-E5: Single node critical path

**Requirement:** 122-REQ-4.E1
**Type:** unit
**Description:** Verify single-node graph has critical path of length 1.

**Preconditions:**
- TaskGraph with one node.

**Input:**
- Single-node graph.

**Expected:**
- Critical path: ["A"], length 1.

**Assertion pseudocode:**
```
graph = make_single_node_graph("A")
path = critical_path(graph)
ASSERT path == ["A"]
```

### TS-122-E6: Empty graph critical path

**Requirement:** 122-REQ-4.E2
**Type:** unit
**Description:** Verify empty graph returns empty critical path.

**Preconditions:**
- TaskGraph with no nodes (empty order).

**Input:**
- Empty graph.

**Expected:**
- Critical path: [].

**Assertion pseudocode:**
```
graph = TaskGraph(nodes={}, edges=[], order=[])
path = critical_path(graph)
ASSERT path == []
```

### TS-122-E7: Analyze with nonexistent --spec

**Requirement:** 122-REQ-5.E1
**Type:** integration
**Description:** Verify error when --dry-run --spec references a
nonexistent spec.

**Preconditions:**
- Specs directory without the requested spec.

**Input:**
- CLI invocation: `plan --dry-run --spec nonexistent_spec`

**Expected:**
- Error message.
- Exit code 1.

**Assertion pseudocode:**
```
result = runner.invoke(plan_cmd, ["--dry-run", "--spec", "nonexistent_spec"], obj={"json": False})
ASSERT result.exit_code == 1
```

## Property Test Cases

### TS-122-P1: Phase completeness

**Property:** Property 1 from design.md
**Validates:** 122-REQ-2.1
**Type:** property
**Description:** All nodes in the graph appear in exactly one phase.

**For any:** Random DAGs with 1-50 nodes and 0-100 edges (acyclic).
**Invariant:** The union of all phase node_ids equals the set of node IDs
in graph.order.

**Assertion pseudocode:**
```
FOR ANY graph IN random_dags(1, 50):
    phases = compute_phases(graph)
    all_ids = [nid for p in phases for nid in p.node_ids]
    ASSERT set(all_ids) == set(graph.order)
    ASSERT len(all_ids) == len(set(all_ids))  # no duplicates
```

### TS-122-P2: Phase ordering respects dependencies

**Property:** Property 2 from design.md
**Validates:** 122-REQ-2.1
**Type:** property
**Description:** For every edge (A→B), A is in an earlier phase than B.

**For any:** Random DAGs with 2-50 nodes.
**Invariant:** For every edge, source phase number < target phase number.

**Assertion pseudocode:**
```
FOR ANY graph IN random_dags(2, 50):
    phases = compute_phases(graph)
    phase_of = {nid: p.number for p in phases for nid in p.node_ids}
    FOR edge IN graph.edges:
        ASSERT phase_of[edge.source] < phase_of[edge.target]
```

### TS-122-P3: Critical path is valid path

**Property:** Property 3 from design.md
**Validates:** 122-REQ-4.1
**Type:** property
**Description:** Every consecutive pair in the critical path is connected
by an edge.

**For any:** Random DAGs with 1-50 nodes.
**Invariant:** For each (path[i], path[i+1]), an edge exists in the graph.

**Assertion pseudocode:**
```
FOR ANY graph IN random_dags(1, 50):
    path = critical_path(graph)
    edge_set = {(e.source, e.target) for e in graph.edges}
    FOR i IN range(len(path) - 1):
        ASSERT (path[i], path[i+1]) in edge_set
```

### TS-122-P4: Critical path is longest

**Property:** Property 4 from design.md
**Validates:** 122-REQ-4.1, 122-REQ-4.3
**Type:** property
**Description:** No source-to-sink path in the graph is longer than the
critical path.

**For any:** Random DAGs with 1-30 nodes (smaller for exhaustive check).
**Invariant:** The length of the critical path >= length of every other
source-to-sink path.

**Assertion pseudocode:**
```
FOR ANY graph IN random_dags(1, 30):
    cp = critical_path(graph)
    all_paths = enumerate_all_source_to_sink_paths(graph)
    FOR p IN all_paths:
        ASSERT len(cp) >= len(p)
```

### TS-122-P5: Analyze does not persist

**Property:** Property 5 from design.md
**Validates:** 122-REQ-1.1, 122-REQ-6.1
**Type:** property
**Description:** run_plan with dry_run=True never calls save_plan.

**For any:** Random valid configs with dry_run=True.
**Invariant:** save_plan is never invoked.

**Assertion pseudocode:**
```
FOR ANY config IN valid_configs():
    with patch("agent_fox.graph.planner.save_plan") as mock:
        run_plan(config, dry_run=True)
        ASSERT mock.call_count == 0
```

### TS-122-P6: Edge grouping exhaustive

**Property:** Property 6 from design.md
**Validates:** 122-REQ-3.1
**Type:** property
**Description:** All edges appear in exactly one group.

**For any:** Random DAGs with mixed edge kinds.
**Invariant:** len(intra_spec) + len(cross_spec) == len(graph.edges).

**Assertion pseudocode:**
```
FOR ANY graph IN random_dags_with_mixed_edges():
    grouped = group_edges(graph)
    ASSERT len(grouped.intra_spec) + len(grouped.cross_spec) == len(graph.edges)
```

### TS-122-P7: Critical path determinism

**Property:** Property 7 from design.md
**Validates:** 122-REQ-4.3
**Type:** property
**Description:** Two calls to critical_path on the same graph return the
same result.

**For any:** Random DAGs.
**Invariant:** critical_path(g) == critical_path(g) for the same g.

**Assertion pseudocode:**
```
FOR ANY graph IN random_dags(1, 50):
    ASSERT critical_path(graph) == critical_path(graph)
```

### TS-122-P8: Phase determinism

**Property:** Property 8 from design.md
**Validates:** 122-REQ-2.1
**Type:** property
**Description:** Two calls to compute_phases on the same graph return the
same result.

**For any:** Random DAGs.
**Invariant:** compute_phases(g) == compute_phases(g) for the same g.

**Assertion pseudocode:**
```
FOR ANY graph IN random_dags(1, 50):
    p1 = compute_phases(graph)
    p2 = compute_phases(graph)
    ASSERT p1 == p2
```

## Integration Smoke Tests

### TS-122-SMOKE-1: Analyze human-readable end-to-end

**Execution Path:** Path 1 from design.md
**Description:** Full CLI invocation of `plan --dry-run` produces
human-readable analysis output without database persistence.

**Setup:** Create a temporary specs directory with two specs (spec_a with
3 task groups, spec_b with 2 task groups and a cross-spec dependency on
spec_a). Mock `check_pid_file` to return no daemon. Do NOT mock
`build_plan`, `compute_phases`, `critical_path`, or `group_edges`.

**Trigger:** `runner.invoke(plan_cmd, ["--dry-run"], obj={"json": False})`

**Expected side effects:**
- stdout contains "Plan Analysis", "Parallelism Phases", "Critical Path",
  "Dependency Edges".
- stdout contains all spec_a and spec_b node IDs.
- Exit code 0.
- No database file created or modified.

**Must NOT satisfy with:** Mocking `build_plan`, `compute_phases`,
`critical_path`, or `group_edges`.

**Assertion pseudocode:**
```
specs_dir = create_temp_specs(spec_a=3_groups, spec_b=2_groups_dep_on_a)
with patch("agent_fox.cli.plan.check_pid_file", return_value=(PidStatus.ABSENT, None)):
    result = runner.invoke(plan_cmd, ["--dry-run", "--specs-dir", str(specs_dir)], obj={"json": False})
    ASSERT result.exit_code == 0
    ASSERT "Plan Analysis" in result.output
    ASSERT "Parallelism Phases" in result.output
    ASSERT "Critical Path" in result.output
    ASSERT "Dependency Edges" in result.output
```

### TS-122-SMOKE-2: Analyze JSON end-to-end

**Execution Path:** Path 2 from design.md
**Description:** Full CLI invocation of `plan --dry-run --json` produces
valid JSON with all analysis keys.

**Setup:** Same as SMOKE-1. Do NOT mock planning or analysis components.

**Trigger:** `runner.invoke(plan_cmd, ["--dry-run"], obj={"json": True})`

**Expected side effects:**
- stdout is valid JSON.
- JSON has keys: nodes, edges, order, metadata, phases, critical_path,
  grouped_edges.
- Exit code 0.

**Must NOT satisfy with:** Mocking `build_plan`, `compute_phases`,
`critical_path`, or `group_edges`.

**Assertion pseudocode:**
```
result = runner.invoke(plan_cmd, ["--dry-run", "--specs-dir", str(specs_dir)], obj={"json": True})
ASSERT result.exit_code == 0
data = json.loads(result.output)
for key in ["nodes", "edges", "order", "metadata", "phases", "critical_path", "grouped_edges"]:
    ASSERT key in data
```

### TS-122-SMOKE-3: Normal plan persists (regression)

**Execution Path:** Path 3 from design.md
**Description:** Full CLI invocation of `plan` (without --dry-run) still
persists to DuckDB.

**Setup:** Temp specs directory. Mock `open_knowledge_store` to return a
mock connection (avoid real DB) but do NOT mock `save_plan` — verify it
is called with the graph.

**Trigger:** `runner.invoke(plan_cmd, [], obj={"json": False})`

**Expected side effects:**
- `save_plan` called exactly once.
- Exit code 0.

**Must NOT satisfy with:** Mocking `save_plan`.

**Assertion pseudocode:**
```
with patch("agent_fox.cli.plan.save_plan") as mock_save:
    with patch("agent_fox.cli.plan.open_knowledge_store") as mock_db:
        mock_db.return_value.__enter__ = mock_db.return_value
        result = runner.invoke(plan_cmd, ["--specs-dir", str(specs_dir)], obj={"json": False})
        ASSERT result.exit_code == 0
        ASSERT mock_save.call_count == 1
```

### TS-122-SMOKE-4: run_plan API dry-run mode

**Execution Path:** Path 4 from design.md
**Description:** Calling `run_plan(dry_run=True)` returns a TaskGraph
without any DB interaction.

**Setup:** Valid config and specs directory. Do NOT mock `build_plan`.

**Trigger:** `run_plan(config, dry_run=True, specs_dir=specs_dir)`

**Expected side effects:**
- Returns a TaskGraph with non-empty nodes and order.
- `open_knowledge_store` is never called.
- `save_plan` is never called.

**Must NOT satisfy with:** Mocking `build_plan` or returning a pre-built
graph.

**Assertion pseudocode:**
```
with patch("agent_fox.graph.planner.save_plan") as mock_save:
    with patch("agent_fox.graph.planner.open_knowledge_store") as mock_db:
        graph = run_plan(config, dry_run=True, specs_dir=specs_dir)
        ASSERT isinstance(graph, TaskGraph)
        ASSERT len(graph.nodes) > 0
        ASSERT mock_save.call_count == 0
        ASSERT mock_db.call_count == 0
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 122-REQ-1.1 | TS-122-1 | integration |
| 122-REQ-1.2 | TS-122-2 | integration |
| 122-REQ-1.3 | TS-122-3 | integration |
| 122-REQ-1.E1 | TS-122-E1 | integration |
| 122-REQ-1.E2 | TS-122-E2 | integration |
| 122-REQ-2.1 | TS-122-4 | unit |
| 122-REQ-2.2 | TS-122-5 | unit |
| 122-REQ-2.3 | TS-122-6 | unit |
| 122-REQ-2.E1 | TS-122-E3 | unit |
| 122-REQ-3.1 | TS-122-7 | unit |
| 122-REQ-3.2 | TS-122-8 | unit |
| 122-REQ-3.E1 | TS-122-E4 | unit |
| 122-REQ-4.1 | TS-122-9 | unit |
| 122-REQ-4.2 | TS-122-10 | unit |
| 122-REQ-4.3 | TS-122-11 | unit |
| 122-REQ-4.E1 | TS-122-E5 | unit |
| 122-REQ-4.E2 | TS-122-E6 | unit |
| 122-REQ-5.1 | TS-122-12 | integration |
| 122-REQ-5.2 | TS-122-13 | integration |
| 122-REQ-5.3 | TS-122-14 | integration |
| 122-REQ-5.4 | TS-122-15 | integration |
| 122-REQ-5.E1 | TS-122-E7 | integration |
| 122-REQ-6.1 | TS-122-16 | unit |
| 122-REQ-6.2 | TS-122-17 | unit |
| Property 1 | TS-122-P1 | property |
| Property 2 | TS-122-P2 | property |
| Property 3 | TS-122-P3 | property |
| Property 4 | TS-122-P4 | property |
| Property 5 | TS-122-P5 | property |
| Property 6 | TS-122-P6 | property |
| Property 7 | TS-122-P7 | property |
| Property 8 | TS-122-P8 | property |
