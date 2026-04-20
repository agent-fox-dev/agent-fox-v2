# Test Specification: Plan Analysis and Dependency Quality

## Overview

Tests for parallelism analysis, critical path computation, coarse-dependency
lint rule, circular-dependency lint rule, auto-fix for coarse dependencies
and missing verification steps, the `--analyze` CLI flag, and the `--fix`
CLI flag.

## Test Cases

### TS-20-1: Phase grouping on a diamond graph

**Requirement:** 20-REQ-1.2, 20-REQ-1.3
**Type:** unit
**Description:** Verify nodes are grouped into correct phases on a diamond
DAG (A -> B, A -> C, B -> D, C -> D).

**Preconditions:**
- A TaskGraph with 4 nodes and diamond edges.

**Input:**
- `analyze_plan(diamond_graph)`

**Expected:**
- Phase 1: [A] (1 worker)
- Phase 2: [B, C] (2 workers)
- Phase 3: [D] (1 worker)

**Assertion pseudocode:**
```
analysis = analyze_plan(diamond_graph)
ASSERT len(analysis.phases) == 3
ASSERT set(analysis.phases[0].node_ids) == {"A"}
ASSERT set(analysis.phases[1].node_ids) == {"B", "C"}
ASSERT set(analysis.phases[2].node_ids) == {"D"}
ASSERT analysis.phases[1].worker_count == 2
```

---

### TS-20-2: Phase grouping on a linear chain

**Requirement:** 20-REQ-1.2, 20-REQ-1.E2
**Type:** unit
**Description:** Verify a fully serial graph has one node per phase.

**Preconditions:**
- A TaskGraph with 4 nodes in a chain: A -> B -> C -> D.

**Input:**
- `analyze_plan(chain_graph)`

**Expected:**
- 4 phases, each with 1 node.
- Peak parallelism is 1.

**Assertion pseudocode:**
```
analysis = analyze_plan(chain_graph)
ASSERT len(analysis.phases) == 4
ASSERT all(p.worker_count == 1 for p in analysis.phases)
ASSERT analysis.peak_parallelism == 1
```

---

### TS-20-3: Peak parallelism on a wide graph

**Requirement:** 20-REQ-1.4
**Type:** unit
**Description:** Verify peak parallelism on a graph with a wide middle tier.

**Preconditions:**
- A TaskGraph: A -> {B, C, D, E} -> F (fan-out then fan-in).

**Input:**
- `analyze_plan(wide_graph)`

**Expected:**
- Peak parallelism is 4 (phase 2 has B, C, D, E).
- Total phases is 3.

**Assertion pseudocode:**
```
analysis = analyze_plan(wide_graph)
ASSERT analysis.peak_parallelism == 4
ASSERT analysis.total_phases == 3
```

---

### TS-20-4: Critical path on a diamond graph

**Requirement:** 20-REQ-2.1, 20-REQ-2.2
**Type:** unit
**Description:** Verify critical path is computed correctly on a diamond.

**Preconditions:**
- Diamond graph: A -> B -> D, A -> C -> D.

**Input:**
- `analyze_plan(diamond_graph)`

**Expected:**
- Critical path length is 3 (e.g., A -> B -> D or A -> C -> D).
- Critical path contains 3 nodes.

**Assertion pseudocode:**
```
analysis = analyze_plan(diamond_graph)
ASSERT analysis.critical_path_length == 3
ASSERT len(analysis.critical_path) == 3
ASSERT analysis.critical_path[0] == "A"
ASSERT analysis.critical_path[-1] == "D"
```

---

### TS-20-5: Float computation

**Requirement:** 20-REQ-2.3
**Type:** unit
**Description:** Verify float is computed correctly. In a graph with a
shortcut (A -> B -> C -> D, A -> D), node D has ES=1 via shortcut but
ES=3 via chain. B and C should have float 0 (on the critical path).

**Preconditions:**
- Graph: A -> B -> C -> D, and A -> D.
- Critical path is A -> B -> C -> D (length 4).
- D also reachable via A -> D (length 2), but the longer path dominates.

**Input:**
- `analyze_plan(graph)`

**Expected:**
- A: float=0, B: float=0, C: float=0, D: float=0
  (all on the critical path since the chain A-B-C-D is the longest)

**Assertion pseudocode:**
```
analysis = analyze_plan(graph)
ASSERT analysis.timings["A"].float == 0
ASSERT analysis.timings["B"].float == 0
ASSERT analysis.timings["C"].float == 0
ASSERT analysis.timings["D"].float == 0
```

---

### TS-20-6: Float on non-critical nodes

**Requirement:** 20-REQ-2.3, 20-REQ-2.4
**Type:** unit
**Description:** Verify float > 0 for nodes not on the critical path.

**Preconditions:**
- Graph: A -> B -> C -> F, A -> D -> F, A -> E -> F.
- Critical path: A -> B -> C -> F (length 4).
- D has float 1 (ES=1, LS=2).
- E has float 1 (ES=1, LS=2).

**Input:**
- `analyze_plan(graph)`

**Expected:**
- D.float > 0
- E.float > 0
- A.float == 0, B.float == 0, C.float == 0, F.float == 0

**Assertion pseudocode:**
```
analysis = analyze_plan(graph)
ASSERT analysis.timings["D"].float > 0
ASSERT analysis.timings["E"].float > 0
ASSERT analysis.timings["A"].float == 0
ASSERT analysis.timings["F"].float == 0
```

---

### TS-20-7: Empty graph analysis

**Requirement:** 20-REQ-1.E1
**Type:** unit
**Description:** Verify empty graph produces empty analysis.

**Preconditions:**
- A TaskGraph with no nodes.

**Input:**
- `analyze_plan(empty_graph)`

**Expected:**
- 0 phases, critical path length 0, peak parallelism 0.

**Assertion pseudocode:**
```
analysis = analyze_plan(empty_graph)
ASSERT analysis.total_phases == 0
ASSERT analysis.critical_path_length == 0
ASSERT analysis.peak_parallelism == 0
```

---

### TS-20-8: Coarse dependency detected

**Requirement:** 20-REQ-3.1, 20-REQ-3.2, 20-REQ-3.3
**Type:** unit
**Description:** Verify lint rule flags specs using standard dep format.

**Preconditions:**
- A spec with prd.md containing:
  `| This Spec | Depends On | What It Uses |`

**Input:**
- `_check_coarse_dependency(spec_name, prd_path)`

**Expected:**
- Returns 1 Warning-severity finding.
- Message mentions "group-level" or "From Group".

**Assertion pseudocode:**
```
findings = _check_coarse_dependency("02_beta", prd_path)
ASSERT len(findings) == 1
ASSERT findings[0].severity == "warning"
ASSERT "group-level" in findings[0].message.lower() or "from group" in findings[0].message.lower()
```

---

### TS-20-9: Group-level dependency produces no finding

**Requirement:** 20-REQ-3.E2
**Type:** unit
**Description:** Verify lint rule does not flag group-level format.

**Preconditions:**
- A spec with prd.md containing:
  `| Spec | From Group | To Group | Relationship |`

**Input:**
- `_check_coarse_dependency(spec_name, prd_path)`

**Expected:**
- Returns empty list (no findings).

**Assertion pseudocode:**
```
findings = _check_coarse_dependency("02_beta", prd_path)
ASSERT len(findings) == 0
```

---

### TS-20-10: No dependency table produces no finding

**Requirement:** 20-REQ-3.E1
**Type:** unit
**Description:** Verify lint rule produces nothing when no dep table exists.

**Preconditions:**
- A spec with prd.md containing no dependency table.

**Input:**
- `_check_coarse_dependency(spec_name, prd_path)`

**Expected:**
- Returns empty list.

**Assertion pseudocode:**
```
findings = _check_coarse_dependency("01_alpha", prd_path)
ASSERT len(findings) == 0
```

---

### TS-20-11: Circular dependency detected

**Requirement:** 20-REQ-4.1, 20-REQ-4.3
**Type:** unit
**Description:** Verify cycle detection across specs.

**Preconditions:**
- Three specs: A depends on B, B depends on C, C depends on A.
- Each spec has a prd.md with appropriate dependency table.

**Input:**
- `_check_circular_dependency(specs)`

**Expected:**
- Returns at least 1 Error-severity finding.
- Message lists spec names involved in the cycle.

**Assertion pseudocode:**
```
findings = _check_circular_dependency(specs)
ASSERT len(findings) >= 1
ASSERT findings[0].severity == "error"
ASSERT "A" in findings[0].message or "B" in findings[0].message
```

---

### TS-20-12: Acyclic dependencies produce no cycle finding

**Requirement:** 20-REQ-4.2
**Type:** unit
**Description:** Verify no false positives on acyclic dependency graph.

**Preconditions:**
- Specs: A -> B -> C (linear, no cycle).

**Input:**
- `_check_circular_dependency(specs)`

**Expected:**
- Returns empty list.

**Assertion pseudocode:**
```
findings = _check_circular_dependency(specs)
ASSERT len(findings) == 0
```

---

### TS-20-13: Missing spec reference skipped in cycle detection

**Requirement:** 20-REQ-4.E1
**Type:** unit
**Description:** Verify edges to non-existent specs are skipped.

**Preconditions:**
- Spec A depends on "99_nonexistent" (not in discovered set).

**Input:**
- `_check_circular_dependency(specs)`

**Expected:**
- Returns empty list (no cycle, dangling ref ignored).

**Assertion pseudocode:**
```
findings = _check_circular_dependency(specs)
ASSERT len(findings) == 0
```

---

### TS-20-14: Fix coarse dependency rewrites table

**Requirement:** 20-REQ-6.3
**Type:** unit
**Description:** Verify fixer rewrites standard-format table to alt format.

**Preconditions:**
- A prd.md with standard-format dependency table:
  ```
  | This Spec | Depends On | What It Uses |
  |-----------|-----------|-------------|
  | 02_beta | 01_alpha | Uses Config for settings |
  ```
- known_specs = {"01_alpha": [1, 2, 3], "02_beta": [1, 2]}

**Input:**
- `fix_coarse_dependency("02_beta", prd_path, known_specs, [1, 2])`

**Expected:**
- prd.md now contains alt-format table:
  ```
  | Spec | From Group | To Group | Relationship |
  |------|-----------|----------|--------------|
  | 01_alpha | 3 | 1 | Uses Config for settings |
  ```
- Returns 1 FixResult.

**Assertion pseudocode:**
```
results = fix_coarse_dependency("02_beta", prd_path, known_specs, [1, 2])
ASSERT len(results) == 1
ASSERT results[0].rule == "coarse-dependency"
content = prd_path.read_text()
ASSERT "From Group" in content
ASSERT "This Spec" not in content
ASSERT "01_alpha | 3 | 1" in content
```

---

### TS-20-15: Fix coarse dependency with unknown upstream groups

**Requirement:** 20-REQ-6.E2
**Type:** unit
**Description:** Verify fixer uses sentinel 0 when upstream has no tasks.md.

**Preconditions:**
- A prd.md with standard dep table referencing "03_gamma".
- known_specs = {"03_gamma": []}  (no task groups)

**Input:**
- `fix_coarse_dependency("02_beta", prd_path, known_specs, [1])`

**Expected:**
- From Group is 0 in the rewritten table.

**Assertion pseudocode:**
```
results = fix_coarse_dependency("02_beta", prd_path, known_specs, [1])
content = prd_path.read_text()
ASSERT "03_gamma | 0 | 1" in content
```

---

### TS-20-16: Fix coarse dependency is idempotent

**Requirement:** 20-REQ-6.2
**Type:** unit
**Description:** Verify running fixer twice produces same result.

**Preconditions:**
- A prd.md with standard-format dependency table.

**Input:**
- `fix_coarse_dependency(...)` called twice.

**Expected:**
- First call returns 1 FixResult and rewrites the file.
- Second call returns 0 FixResults (no standard table found).
- File content is identical after both calls.

**Assertion pseudocode:**
```
results1 = fix_coarse_dependency("02_beta", prd_path, known_specs, [1])
content1 = prd_path.read_text()
results2 = fix_coarse_dependency("02_beta", prd_path, known_specs, [1])
content2 = prd_path.read_text()
ASSERT len(results1) == 1
ASSERT len(results2) == 0
ASSERT content1 == content2
```

---

### TS-20-17: Fix missing verification appends step

**Requirement:** 20-REQ-6.4
**Type:** unit
**Description:** Verify fixer appends verification step to groups missing it.

**Preconditions:**
- A tasks.md with one task group (group 1) that has subtasks 1.1 and 1.2
  but no 1.V.

**Input:**
- `fix_missing_verification("02_beta", tasks_path)`

**Expected:**
- tasks.md now contains `- [ ] 1.V Verify task group 1` after subtask 1.2.
- Returns 1 FixResult.

**Assertion pseudocode:**
```
results = fix_missing_verification("02_beta", tasks_path)
ASSERT len(results) == 1
content = tasks_path.read_text()
ASSERT "1.V Verify task group 1" in content
```

---

### TS-20-18: Fix missing verification skips groups that have it

**Requirement:** 20-REQ-6.4
**Type:** unit
**Description:** Verify fixer does not duplicate existing verification steps.

**Preconditions:**
- A tasks.md with group 1 that already has subtask 1.V.

**Input:**
- `fix_missing_verification("02_beta", tasks_path)`

**Expected:**
- Returns empty list. File unchanged.

**Assertion pseudocode:**
```
results = fix_missing_verification("02_beta", tasks_path)
ASSERT len(results) == 0
```

---

### TS-20-19: apply_fixes skips unfixable findings

**Requirement:** 20-REQ-6.E4
**Type:** unit
**Description:** Verify unfixable findings pass through unchanged.

**Preconditions:**
- Findings include circular-dependency (Error) and coarse-dependency (Warning).

**Input:**
- `apply_fixes(findings, specs, specs_dir, known_specs)`

**Expected:**
- Only coarse-dependency is fixed.
- circular-dependency remains in post-fix validation.

**Assertion pseudocode:**
```
results = apply_fixes(findings, specs, specs_dir, known_specs)
rules_fixed = {r.rule for r in results}
ASSERT "coarse-dependency" in rules_fixed
ASSERT "circular-dependency" not in rules_fixed
```

---

### TS-20-20: --fix with no fixable findings is a no-op

**Requirement:** 20-REQ-6.E1
**Type:** unit
**Description:** Verify --fix does not modify files when nothing is fixable.

**Preconditions:**
- All specs use group-level format, all groups have verification steps.

**Input:**
- `apply_fixes(findings, specs, specs_dir, known_specs)`

**Expected:**
- Returns empty list. No files modified.

**Assertion pseudocode:**
```
results = apply_fixes([], specs, specs_dir, known_specs)
ASSERT len(results) == 0
```

## Edge Case Tests

### TS-20-E1: Tied critical paths

**Requirement:** 20-REQ-2.E1
**Type:** unit
**Description:** Verify tied critical paths are handled.

**Preconditions:**
- Graph: A -> B -> D, A -> C -> D. Both paths have length 3.

**Input:**
- `analyze_plan(diamond_graph)`

**Expected:**
- `has_alternative_critical_paths` is True.
- Critical path length is 3.

**Assertion pseudocode:**
```
analysis = analyze_plan(diamond_graph)
ASSERT analysis.has_alternative_critical_paths == True
ASSERT analysis.critical_path_length == 3
```

## Property Test Cases

### TS-20-P1: Phase completeness

**Property:** Property 1 from design.md
**Validates:** 20-REQ-1.2
**Type:** property
**Description:** Every node appears in exactly one phase.

**For any:** randomly generated DAG with 1-30 nodes
**Invariant:** Union of all phase node_ids equals the set of all graph
node IDs.

**Assertion pseudocode:**
```
FOR ANY dag IN random_dags(max_nodes=30):
    analysis = analyze_plan(dag)
    all_phase_nodes = set()
    for phase in analysis.phases:
        overlap = all_phase_nodes & set(phase.node_ids)
        ASSERT len(overlap) == 0  # no duplicates
        all_phase_nodes |= set(phase.node_ids)
    ASSERT all_phase_nodes == set(dag.nodes.keys())
```

---

### TS-20-P2: Phase ordering respects dependencies

**Property:** Property 2 from design.md
**Validates:** 20-REQ-1.2
**Type:** property
**Description:** For every edge, source phase < target phase.

**For any:** randomly generated DAG with 1-30 nodes
**Invariant:** For every edge (A -> B), phase_of(A) < phase_of(B).

**Assertion pseudocode:**
```
FOR ANY dag IN random_dags(max_nodes=30):
    analysis = analyze_plan(dag)
    node_to_phase = {}
    for phase in analysis.phases:
        for nid in phase.node_ids:
            node_to_phase[nid] = phase.phase_number
    FOR EACH edge IN dag.edges:
        ASSERT node_to_phase[edge.source] < node_to_phase[edge.target]
```

---

### TS-20-P3: Critical path equals makespan

**Property:** Property 3 from design.md
**Validates:** 20-REQ-2.1
**Type:** property
**Description:** Critical path length equals number of phases.

**For any:** randomly generated DAG with 1-30 nodes
**Invariant:** `analysis.critical_path_length == analysis.total_phases`

**Assertion pseudocode:**
```
FOR ANY dag IN random_dags(max_nodes=30):
    analysis = analyze_plan(dag)
    ASSERT analysis.critical_path_length == analysis.total_phases
```

---

### TS-20-P4: Zero float implies critical path membership

**Property:** Property 4 from design.md
**Validates:** 20-REQ-2.3
**Type:** property
**Description:** Nodes with float 0 are on the critical path; nodes with
float > 0 are not.

**For any:** randomly generated DAG with 1-30 nodes
**Invariant:** `{n for n, t in timings if t.float == 0} == set(critical_path)`

**Assertion pseudocode:**
```
FOR ANY dag IN random_dags(max_nodes=30):
    analysis = analyze_plan(dag)
    zero_float = {nid for nid, t in analysis.timings.items() if t.float == 0}
    ASSERT zero_float == set(analysis.critical_path)
```

---

### TS-20-P5: Float is non-negative

**Property:** Property 5 from design.md
**Validates:** 20-REQ-2.3
**Type:** property
**Description:** No node has negative float.

**For any:** randomly generated DAG with 1-30 nodes
**Invariant:** All float values >= 0.

**Assertion pseudocode:**
```
FOR ANY dag IN random_dags(max_nodes=30):
    analysis = analyze_plan(dag)
    FOR EACH timing IN analysis.timings.values():
        ASSERT timing.float >= 0
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 20-REQ-1.1 | TS-20-1 | unit |
| 20-REQ-1.2 | TS-20-1, TS-20-2 | unit |
| 20-REQ-1.3 | TS-20-1 | unit |
| 20-REQ-1.4 | TS-20-3 | unit |
| 20-REQ-1.E1 | TS-20-7 | unit |
| 20-REQ-1.E2 | TS-20-2 | unit |
| 20-REQ-2.1 | TS-20-4 | unit |
| 20-REQ-2.2 | TS-20-4 | unit |
| 20-REQ-2.3 | TS-20-5, TS-20-6 | unit |
| 20-REQ-2.4 | TS-20-6 | unit |
| 20-REQ-2.E1 | TS-20-E1 | unit |
| 20-REQ-3.1 | TS-20-8 | unit |
| 20-REQ-3.2 | TS-20-8 | unit |
| 20-REQ-3.3 | TS-20-8 | unit |
| 20-REQ-3.E1 | TS-20-10 | unit |
| 20-REQ-3.E2 | TS-20-9 | unit |
| 20-REQ-4.1 | TS-20-11 | unit |
| 20-REQ-4.2 | TS-20-12 | unit |
| 20-REQ-4.3 | TS-20-11 | unit |
| 20-REQ-4.E1 | TS-20-13 | unit |
| 20-REQ-4.E2 | TS-20-12 | unit |
| 20-REQ-5.1 | -- | manual review |
| 20-REQ-5.2 | -- | manual review |
| 20-REQ-5.3 | -- | manual review |
| 20-REQ-5.E1 | -- | manual review |
| 20-REQ-6.1 | TS-20-14, TS-20-20 | unit |
| 20-REQ-6.2 | TS-20-16 | unit |
| 20-REQ-6.3 | TS-20-14 | unit |
| 20-REQ-6.4 | TS-20-17, TS-20-18 | unit |
| 20-REQ-6.5 | TS-20-14 | unit |
| 20-REQ-6.6 | -- | integration |
| 20-REQ-6.E1 | TS-20-20 | unit |
| 20-REQ-6.E2 | TS-20-15 | unit |
| 20-REQ-6.E3 | -- | unit |
| 20-REQ-6.E4 | TS-20-19 | unit |
| Property 1 | TS-20-P1 | property |
| Property 2 | TS-20-P2 | property |
| Property 3 | TS-20-P3 | property |
| Property 4 | TS-20-P4 | property |
| Property 5 | TS-20-P5 | property |
