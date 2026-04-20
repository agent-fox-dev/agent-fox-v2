# Test Specification: Planning Engine

## Overview

Tests for the planning engine: specification discovery, task parsing, task
graph construction, dependency resolution, fast-mode filtering, plan
persistence, and the `agent-fox plan` CLI command. Tests map to requirements
in `requirements.md` and correctness properties in `design.md`.

## Test Cases

### TS-02-1: Discover spec folders sorted by prefix

**Requirement:** 02-REQ-1.1
**Type:** unit
**Description:** Verify discovery finds spec folders and returns them sorted.

**Preconditions:**
- A temporary `.specs/` directory with folders `03_foo/`, `01_bar/`,
  `02_baz/`, each containing a `tasks.md`.

**Input:**
- `discover_specs(specs_dir=tmp_specs_dir)`

**Expected:**
- Returns 3 `SpecInfo` objects sorted by prefix: 1, 2, 3.
- Names match folder names.

**Assertion pseudocode:**
```
specs = discover_specs(tmp_specs_dir)
ASSERT len(specs) == 3
ASSERT specs[0].prefix == 1
ASSERT specs[1].prefix == 2
ASSERT specs[2].prefix == 3
ASSERT specs[0].name == "01_bar"
```

---

### TS-02-2: Discover with --spec filter

**Requirement:** 02-REQ-1.2
**Type:** unit
**Description:** Verify `--spec` restricts discovery to one specification.

**Preconditions:**
- `.specs/` with `01_alpha/tasks.md`, `02_beta/tasks.md`.

**Input:**
- `discover_specs(specs_dir, filter_spec="02_beta")`

**Expected:**
- Returns exactly 1 `SpecInfo` for `02_beta`.

**Assertion pseudocode:**
```
specs = discover_specs(tmp_specs_dir, filter_spec="02_beta")
ASSERT len(specs) == 1
ASSERT specs[0].name == "02_beta"
```

---

### TS-02-3: Parse task groups from tasks.md

**Requirement:** 02-REQ-2.1, 02-REQ-2.2, 02-REQ-2.4
**Type:** unit
**Description:** Verify parser extracts task groups with subtasks.

**Preconditions:**
- A `tasks.md` file with two task groups, the first having 3 subtasks.

**Input:**
- `parse_tasks(tasks_path)`

**Expected:**
- Returns 2 `TaskGroupDef` objects.
- First group has number=1, 3 subtasks, non-empty title and body.
- Second group has number=2.

**Assertion pseudocode:**
```
groups = parse_tasks(tasks_path)
ASSERT len(groups) == 2
ASSERT groups[0].number == 1
ASSERT len(groups[0].subtasks) == 3
ASSERT groups[0].title != ""
ASSERT groups[1].number == 2
```

---

### TS-02-4: Parse optional task marker

**Requirement:** 02-REQ-2.3
**Type:** unit
**Description:** Verify parser detects the `*` optional marker.

**Preconditions:**
- A `tasks.md` with `- [ ] * 3. Polish and cleanup`.

**Input:**
- `parse_tasks(tasks_path)`

**Expected:**
- The task group with number=3 has `optional=True`.
- Other groups have `optional=False`.

**Assertion pseudocode:**
```
groups = parse_tasks(tasks_path)
optional_group = [g for g in groups if g.number == 3][0]
ASSERT optional_group.optional == True
ASSERT optional_group.title == "Polish and cleanup"
non_optional = [g for g in groups if g.number != 3]
ASSERT all(not g.optional for g in non_optional)
```

---

### TS-02-5: Build graph with intra-spec edges

**Requirement:** 02-REQ-3.1, 02-REQ-3.3, 02-REQ-3.4
**Type:** unit
**Description:** Verify builder creates sequential edges within a spec.

**Preconditions:**
- One spec with 3 task groups.

**Input:**
- `build_graph(specs, task_groups, cross_deps=[])`

**Expected:**
- 3 nodes with IDs `spec:1`, `spec:2`, `spec:3`.
- 2 edges: `spec:1 -> spec:2`, `spec:2 -> spec:3`.
- All nodes have status `pending`.

**Assertion pseudocode:**
```
graph = build_graph(specs, {"my_spec": [g1, g2, g3]}, [])
ASSERT len(graph.nodes) == 3
ASSERT all(n.status == NodeStatus.PENDING for n in graph.nodes.values())
edges = [(e.source, e.target) for e in graph.edges]
ASSERT ("my_spec:1", "my_spec:2") IN edges
ASSERT ("my_spec:2", "my_spec:3") IN edges
```

---

### TS-02-6: Build graph with cross-spec edges

**Requirement:** 02-REQ-3.2
**Type:** unit
**Description:** Verify builder adds cross-spec dependency edges.

**Preconditions:**
- Two specs: `01_alpha` (2 groups), `02_beta` (2 groups).
- Cross-dep: `02_beta` depends on `01_alpha`.

**Input:**
- `build_graph(specs, task_groups, cross_deps=[dep])`

**Expected:**
- Edge from `01_alpha:2` (last group of alpha) to `02_beta:1` (first
  group of beta) exists.

**Assertion pseudocode:**
```
dep = CrossSpecDep("02_beta", 1, "01_alpha", 2)
graph = build_graph(specs, groups, [dep])
edges = [(e.source, e.target) for e in graph.edges]
ASSERT ("01_alpha:2", "02_beta:1") IN edges
```

---

### TS-02-7: Topological sort produces valid order

**Requirement:** 02-REQ-4.1, 02-REQ-4.2
**Type:** unit
**Description:** Verify resolver returns a valid topological ordering.

**Preconditions:**
- A graph with A -> B -> C and A -> C.

**Input:**
- `resolve_order(graph)`

**Expected:**
- A appears before B and C; B appears before C.

**Assertion pseudocode:**
```
order = resolve_order(graph)
ASSERT order.index("A") < order.index("B")
ASSERT order.index("A") < order.index("C")
ASSERT order.index("B") < order.index("C")
```

---

### TS-02-8: Fast mode removes optional tasks

**Requirement:** 02-REQ-5.1, 02-REQ-5.3
**Type:** unit
**Description:** Verify fast mode excludes optional nodes and marks them skipped.

**Preconditions:**
- A graph with 3 nodes: A (required), B (optional), C (required).
  Edges: A -> B -> C.

**Input:**
- `apply_fast_mode(graph)`

**Expected:**
- B has status `SKIPPED`.
- Ordering contains only A and C.
- Metadata flag `fast_mode` is True.

**Assertion pseudocode:**
```
result = apply_fast_mode(graph)
ASSERT result.nodes["B"].status == NodeStatus.SKIPPED
ASSERT "B" NOT IN result.order
ASSERT len(result.order) == 2
```

---

### TS-02-9: Fast mode rewires dependencies

**Requirement:** 02-REQ-5.2
**Type:** unit
**Description:** Verify fast mode creates direct edge when optional node removed.

**Preconditions:**
- Edges: A -> B (optional) -> C.

**Input:**
- `apply_fast_mode(graph)`

**Expected:**
- New edge A -> C exists.
- No edges reference B.

**Assertion pseudocode:**
```
result = apply_fast_mode(graph)
edges = [(e.source, e.target) for e in result.edges]
ASSERT ("A", "C") IN edges
ASSERT all(e.source != "B" and e.target != "B" for e in result.edges)
```

---

### TS-02-10: Plan persisted and loaded

**Requirement:** 02-REQ-6.1, 02-REQ-6.2, 02-REQ-6.3
**Type:** integration
**Description:** Verify plan is saved to JSON and can be reloaded.

**Preconditions:**
- A temporary `.agent-fox/` directory.
- A valid TaskGraph.

**Input:**
- Serialize graph to `plan.json`, then load it back.

**Expected:**
- Loaded graph has same nodes, edges, and order.
- Metadata contains `created_at` and `version`.

**Assertion pseudocode:**
```
save_plan(graph, plan_path)
loaded = load_plan(plan_path)
ASSERT loaded.nodes.keys() == graph.nodes.keys()
ASSERT len(loaded.edges) == len(graph.edges)
ASSERT loaded.order == graph.order
ASSERT loaded.metadata.created_at != ""
```

---

### TS-02-11: Plan CLI command end-to-end

**Requirement:** 02-REQ-7.1, 02-REQ-7.2, 02-REQ-7.3, 02-REQ-7.4
**Type:** integration
**Description:** Verify `agent-fox plan` discovers specs and produces output.

**Preconditions:**
- A temporary project with `.specs/01_test/tasks.md` and
  `.agent-fox/config.toml`.

**Input:**
- CLI invocation: `["plan"]`

**Expected:**
- Exit code 0.
- Output contains task count and spec name.
- `.agent-fox/plan.json` exists.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["plan"])
ASSERT result.exit_code == 0
ASSERT "01_test" IN result.output
ASSERT plan_json_path.exists()
```

## Property Test Cases

### TS-02-P1: Topological order validity

**Property:** Property 1 from design.md
**Validates:** 02-REQ-4.1
**Type:** property
**Description:** For any acyclic graph, topological order respects all edges.

**For any:** randomly generated DAG with 1-20 nodes and valid edges
**Invariant:** For every edge (A -> B), `order.index(A) < order.index(B)`.

**Assertion pseudocode:**
```
FOR ANY dag IN random_dags(max_nodes=20):
    order = resolve_order(dag)
    FOR EACH edge IN dag.edges:
        ASSERT order.index(edge.source) < order.index(edge.target)
```

---

### TS-02-P2: Fast-mode dependency preservation

**Property:** Property 2 from design.md
**Validates:** 02-REQ-5.2
**Type:** property
**Description:** Removing optional nodes preserves reachability.

**For any:** graph with at least one optional node having both predecessors
and successors
**Invariant:** After fast mode, every successor of the removed node is
reachable from every predecessor.

**Assertion pseudocode:**
```
FOR ANY graph IN graphs_with_optional_nodes():
    result = apply_fast_mode(graph)
    FOR EACH removed IN optional_nodes(graph):
        FOR EACH pred IN graph.predecessors(removed.id):
            FOR EACH succ IN graph.successors(removed.id):
                ASSERT is_reachable(result, pred, succ)
```

---

### TS-02-P3: Node ID uniqueness

**Property:** Property 3 from design.md
**Validates:** 02-REQ-3.3
**Type:** property
**Description:** No two nodes share the same ID.

**For any:** set of specs with task groups
**Invariant:** `len(graph.nodes) == len(set(graph.nodes.keys()))`

**Assertion pseudocode:**
```
FOR ANY specs IN random_spec_sets():
    graph = build_graph(specs, task_groups, [])
    ids = list(graph.nodes.keys())
    ASSERT len(ids) == len(set(ids))
```

---

### TS-02-P4: Cycle detection completeness

**Property:** Property 4 from design.md
**Validates:** 02-REQ-3.E2
**Type:** property
**Description:** Any graph with a cycle raises PlanError.

**For any:** graph that contains at least one cycle
**Invariant:** `resolve_order(graph)` raises `PlanError`.

**Assertion pseudocode:**
```
FOR ANY graph IN graphs_with_cycles():
    ASSERT_RAISES PlanError FROM resolve_order(graph)
```

---

### TS-02-P5: Discovery sort order

**Property:** Property 5 from design.md
**Validates:** 02-REQ-1.1
**Type:** property
**Description:** Discovered specs are always sorted by numeric prefix.

**For any:** set of spec folder names with valid NN_ prefixes
**Invariant:** Result prefixes are in non-decreasing order.

**Assertion pseudocode:**
```
FOR ANY folder_names IN valid_spec_names():
    specs = discover_specs(dir_with(folder_names))
    prefixes = [s.prefix for s in specs]
    ASSERT prefixes == sorted(prefixes)
```

## Edge Case Tests

### TS-02-E1: No specs directory

**Requirement:** 02-REQ-1.E1
**Type:** unit
**Description:** Missing `.specs/` raises PlanError.

**Preconditions:**
- No `.specs/` directory exists.

**Input:**
- `discover_specs(nonexistent_path)`

**Expected:**
- `PlanError` raised.
- Message mentions "specifications" or "specs".

**Assertion pseudocode:**
```
ASSERT_RAISES PlanError FROM discover_specs(Path("/tmp/no_specs"))
```

---

### TS-02-E2: Spec filter matches nothing

**Requirement:** 02-REQ-1.E2
**Type:** unit
**Description:** Unknown `--spec` value raises PlanError with available names.

**Preconditions:**
- `.specs/` with `01_alpha/`, `02_beta/`.

**Input:**
- `discover_specs(specs_dir, filter_spec="99_nonexistent")`

**Expected:**
- `PlanError` raised.
- Error message contains at least one available spec name.

**Assertion pseudocode:**
```
ASSERT_RAISES PlanError FROM discover_specs(dir, filter_spec="99_nonexistent")
ASSERT "01_alpha" IN str(error) OR "02_beta" IN str(error)
```

---

### TS-02-E3: Spec folder without tasks.md

**Requirement:** 02-REQ-1.3
**Type:** unit
**Description:** Spec folder with no tasks.md is skipped.

**Preconditions:**
- `.specs/01_alpha/` with no `tasks.md`, `.specs/02_beta/tasks.md` present.

**Input:**
- `discover_specs(specs_dir)`

**Expected:**
- Returns 1 spec (`02_beta`).
- `01_alpha` is returned but with `has_tasks=False`.

**Assertion pseudocode:**
```
specs = discover_specs(dir)
alpha = [s for s in specs if s.name == "01_alpha"][0]
ASSERT alpha.has_tasks == False
```

---

### TS-02-E4: Cycle in dependency graph

**Requirement:** 02-REQ-3.E2
**Type:** unit
**Description:** Cyclic graph raises PlanError listing cycle nodes.

**Preconditions:**
- A graph with edges: A -> B -> C -> A.

**Input:**
- `resolve_order(cyclic_graph)`

**Expected:**
- `PlanError` raised.
- Error message contains at least two node IDs from the cycle.

**Assertion pseudocode:**
```
ASSERT_RAISES PlanError FROM resolve_order(cyclic_graph)
ASSERT "A" IN str(error) OR "B" IN str(error)
```

---

### TS-02-E5: Dangling cross-spec reference

**Requirement:** 02-REQ-3.E1
**Type:** unit
**Description:** Cross-dep referencing non-existent spec raises PlanError.

**Preconditions:**
- Specs: `01_alpha` (2 groups).
- Cross-dep referencing `99_missing`.

**Input:**
- `build_graph(specs, groups, [bad_dep])`

**Expected:**
- `PlanError` raised mentioning `99_missing`.

**Assertion pseudocode:**
```
bad_dep = CrossSpecDep("01_alpha", 1, "99_missing", 1)
ASSERT_RAISES PlanError FROM build_graph(specs, groups, [bad_dep])
ASSERT "99_missing" IN str(error)
```

---

### TS-02-E6: Corrupted plan.json triggers rebuild

**Requirement:** 02-REQ-6.E1
**Type:** unit
**Description:** Invalid JSON in plan.json causes rebuild instead of crash.

**Preconditions:**
- `.agent-fox/plan.json` exists but contains `{invalid json`.

**Input:**
- `load_plan(plan_path)`

**Expected:**
- Returns `None` (signaling rebuild needed).
- Warning logged.

**Assertion pseudocode:**
```
plan_path.write_text("{invalid json")
result = load_plan(plan_path)
ASSERT result is None
```

---

### TS-02-E7: Empty tasks.md

**Requirement:** 02-REQ-2.E1
**Type:** unit
**Description:** tasks.md with no task groups returns empty list.

**Preconditions:**
- A `tasks.md` containing only a heading and no checkbox items.

**Input:**
- `parse_tasks(tasks_path)`

**Expected:**
- Returns empty list.

**Assertion pseudocode:**
```
tasks_path.write_text("# Tasks\n\nNo items here.\n")
groups = parse_tasks(tasks_path)
ASSERT len(groups) == 0
```

---

### TS-02-E8: Non-contiguous group numbers

**Requirement:** 02-REQ-2.E2
**Type:** unit
**Description:** Parser accepts non-contiguous group numbers.

**Preconditions:**
- A `tasks.md` with groups numbered 1, 3, 5.

**Input:**
- `parse_tasks(tasks_path)`

**Expected:**
- Returns 3 groups with numbers [1, 3, 5].

**Assertion pseudocode:**
```
groups = parse_tasks(tasks_path)
ASSERT [g.number for g in groups] == [1, 3, 5]
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 02-REQ-1.1 | TS-02-1 | unit |
| 02-REQ-1.2 | TS-02-2 | unit |
| 02-REQ-1.3 | TS-02-E3 | unit |
| 02-REQ-1.E1 | TS-02-E1 | unit |
| 02-REQ-1.E2 | TS-02-E2 | unit |
| 02-REQ-2.1, 02-REQ-2.2, 02-REQ-2.4 | TS-02-3 | unit |
| 02-REQ-2.3 | TS-02-4 | unit |
| 02-REQ-2.E1 | TS-02-E7 | unit |
| 02-REQ-2.E2 | TS-02-E8 | unit |
| 02-REQ-3.1, 02-REQ-3.3, 02-REQ-3.4 | TS-02-5 | unit |
| 02-REQ-3.2 | TS-02-6 | unit |
| 02-REQ-3.E1 | TS-02-E5 | unit |
| 02-REQ-3.E2 | TS-02-E4 | unit |
| 02-REQ-4.1, 02-REQ-4.2 | TS-02-7 | unit |
| 02-REQ-4.E1 | (covered by TS-02-E7 → empty graph) | unit |
| 02-REQ-5.1, 02-REQ-5.3 | TS-02-8 | unit |
| 02-REQ-5.2 | TS-02-9 | unit |
| 02-REQ-6.1, 02-REQ-6.2, 02-REQ-6.3 | TS-02-10 | integration |
| 02-REQ-6.4 | TS-02-11 (--reanalyze) | integration |
| 02-REQ-6.E1 | TS-02-E6 | unit |
| 02-REQ-7.1, 02-REQ-7.2, 02-REQ-7.3, 02-REQ-7.4 | TS-02-11 | integration |
| Property 1 | TS-02-P1 | property |
| Property 2 | TS-02-P2 | property |
| Property 3 | TS-02-P3 | property |
| Property 4 | TS-02-P4 | property |
| Property 5 | TS-02-P5 | property |
