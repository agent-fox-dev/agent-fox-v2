# Test Specification: Project Model

## Overview

This test specification covers four components: project model aggregation,
critical path computation, file conflict detection, and learned blocking
thresholds. Tests are organized by component with unit, edge case, and
property test categories.

## Test Cases

### Project Model

#### TS-43-1: Build Project Model with Outcomes

**Requirement:** 43-REQ-1.1
**Type:** unit
**Description:** Verify build_project_model returns SpecMetrics from execution history.

**Preconditions:**
- In-memory DuckDB with execution_outcomes and complexity_assessments tables populated.
- Two specs with sessions: spec_a (2 completed, 1 failed) and spec_b (1 completed).

**Input:**
- Call `build_project_model(conn)`.

**Expected:**
- `model.spec_outcomes["spec_a"].session_count == 3`
- `model.spec_outcomes["spec_a"].failure_rate` approximately 0.333
- `model.spec_outcomes["spec_b"].session_count == 1`
- `model.spec_outcomes["spec_b"].failure_rate == 0.0`

**Assertion pseudocode:**
```
model = build_project_model(conn)
ASSERT "spec_a" IN model.spec_outcomes
ASSERT model.spec_outcomes["spec_a"].session_count == 3
ASSERT abs(model.spec_outcomes["spec_a"].failure_rate - 1/3) < 0.01
ASSERT model.spec_outcomes["spec_b"].failure_rate == 0.0
```

#### TS-43-2: Module Stability Computation

**Requirement:** 43-REQ-1.2
**Type:** unit
**Description:** Verify module stability is computed as finding density.

**Preconditions:**
- DuckDB with review_findings for spec_a (6 findings) and execution_outcomes
  showing spec_a has 3 sessions.

**Input:**
- Call `build_project_model(conn)`.

**Expected:**
- `model.module_stability["spec_a"] == 2.0` (6 findings / 3 sessions)

**Assertion pseudocode:**
```
model = build_project_model(conn)
ASSERT model.module_stability["spec_a"] == 2.0
```

#### TS-43-3: Archetype Effectiveness

**Requirement:** 43-REQ-1.3
**Type:** unit
**Description:** Verify archetype effectiveness is success rate per archetype.

**Preconditions:**
- DuckDB with complexity_assessments containing archetype in feature_vector JSON.
- "coder" archetype: 8 completed, 2 failed. "reviewer" archetype: 3 completed, 0 failed.

**Input:**
- Call `build_project_model(conn)`.

**Expected:**
- `model.archetype_effectiveness["coder"]` approximately 0.8
- `model.archetype_effectiveness["reviewer"]` approximately 1.0

**Assertion pseudocode:**
```
model = build_project_model(conn)
ASSERT abs(model.archetype_effectiveness["coder"] - 0.8) < 0.01
ASSERT model.archetype_effectiveness["reviewer"] == 1.0
```

#### TS-43-4: Format Project Model Output

**Requirement:** 43-REQ-1.4
**Type:** unit
**Description:** Verify format_project_model produces human-readable output.

**Preconditions:**
- A ProjectModel with populated spec_outcomes, module_stability, archetype_effectiveness.

**Input:**
- Call `format_project_model(model)`.

**Expected:**
- Output contains "== Project Model =="
- Output contains "spec_outcomes:"
- Output contains "module_stability:"
- Output contains "archetype_effectiveness:"

**Assertion pseudocode:**
```
output = format_project_model(model)
ASSERT "== Project Model ==" IN output
ASSERT "spec_outcomes:" IN output
ASSERT "module_stability:" IN output
ASSERT "archetype_effectiveness:" IN output
```

#### TS-43-E1: Empty Database Returns Empty Model

**Requirement:** 43-REQ-1.E1
**Type:** unit
**Description:** Verify build_project_model handles empty DuckDB gracefully.

**Preconditions:**
- In-memory DuckDB with tables created but no rows.

**Input:**
- Call `build_project_model(conn)`.

**Expected:**
- `model.spec_outcomes == {}`
- `model.module_stability == {}`
- `model.archetype_effectiveness == {}`
- `model.active_drift_areas == []`

**Assertion pseudocode:**
```
model = build_project_model(conn)
ASSERT model.spec_outcomes == {}
ASSERT model.module_stability == {}
ASSERT model.archetype_effectiveness == {}
ASSERT model.active_drift_areas == []
```

#### TS-43-E2: Findings Without Outcomes

**Requirement:** 43-REQ-1.E2
**Type:** unit
**Description:** Verify module stability when findings exist but no outcomes.

**Preconditions:**
- DuckDB with review_findings for spec_x (4 findings) but no execution_outcomes
  for spec_x.

**Input:**
- Call `build_project_model(conn)`.

**Expected:**
- `model.module_stability["spec_x"] == 4.0` (findings / 1 fallback)

**Assertion pseudocode:**
```
model = build_project_model(conn)
ASSERT model.module_stability["spec_x"] == 4.0
```

### Critical Path

#### TS-43-5: Linear Chain Critical Path

**Requirement:** 43-REQ-2.1
**Type:** unit
**Description:** Verify critical path through a simple linear chain.

**Preconditions:**
- Nodes: A, B, C (linear chain A -> B -> C).
- Duration hints: A=100, B=200, C=300.

**Input:**
- Call `compute_critical_path(nodes, edges, durations)`.

**Expected:**
- `result.path == ["A", "B", "C"]`
- `result.total_duration_ms == 600`
- `result.tied_paths == []`

**Assertion pseudocode:**
```
result = compute_critical_path(
    {"A": "pending", "B": "pending", "C": "pending"},
    {"A": [], "B": ["A"], "C": ["B"]},
    {"A": 100, "B": 200, "C": 300},
)
ASSERT result.path == ["A", "B", "C"]
ASSERT result.total_duration_ms == 600
ASSERT result.tied_paths == []
```

#### TS-43-6: Diamond Graph with Tied Paths

**Requirement:** 43-REQ-2.3
**Type:** unit
**Description:** Verify tied path detection in a diamond DAG.

**Preconditions:**
- Nodes: S, A, B, E. Edges: A depends on S, B depends on S, E depends on A and B.
- Duration hints: S=100, A=200, B=200, E=100.

**Input:**
- Call `compute_critical_path(nodes, edges, durations)`.

**Expected:**
- `result.total_duration_ms == 400`
- Both paths [S, A, E] and [S, B, E] are reported (one as primary, one as tied).

**Assertion pseudocode:**
```
result = compute_critical_path(
    {"S": "p", "A": "p", "B": "p", "E": "p"},
    {"S": [], "A": ["S"], "B": ["S"], "E": ["A", "B"]},
    {"S": 100, "A": 200, "B": 200, "E": 100},
)
ASSERT result.total_duration_ms == 400
all_paths = [result.path] + result.tied_paths
ASSERT ["S", "A", "E"] IN all_paths
ASSERT ["S", "B", "E"] IN all_paths
```

#### TS-43-7: Format Critical Path Output

**Requirement:** 43-REQ-2.2
**Type:** unit
**Description:** Verify format_critical_path produces human-readable output.

**Preconditions:**
- A CriticalPathResult with path ["A", "B", "C"] and total_duration_ms 600.

**Input:**
- Call `format_critical_path(result)`.

**Expected:**
- Output contains "== Critical Path =="
- Output contains "A -> B -> C"
- Output contains "600ms"

**Assertion pseudocode:**
```
result = CriticalPathResult(path=["A", "B", "C"], total_duration_ms=600)
output = format_critical_path(result)
ASSERT "== Critical Path ==" IN output
ASSERT "A -> B -> C" IN output
ASSERT "600ms" IN output
```

#### TS-43-E3: Empty Graph

**Requirement:** 43-REQ-2.E1
**Type:** unit
**Description:** Verify compute_critical_path handles empty graph.

**Preconditions:**
- Empty nodes dict.

**Input:**
- Call `compute_critical_path({}, {}, {})`.

**Expected:**
- `result.path == []`
- `result.total_duration_ms == 0`

**Assertion pseudocode:**
```
result = compute_critical_path({}, {}, {})
ASSERT result.path == []
ASSERT result.total_duration_ms == 0
```

#### TS-43-E4: Missing Duration Hint

**Requirement:** 43-REQ-2.E2
**Type:** unit
**Description:** Verify nodes without duration hints are treated as 0ms.

**Preconditions:**
- Nodes: A, B. A depends on nothing, B depends on A.
- Duration hints: only A=100 (B missing).

**Input:**
- Call `compute_critical_path(nodes, edges, {"A": 100})`.

**Expected:**
- `result.total_duration_ms == 100` (B contributes 0ms)

**Assertion pseudocode:**
```
result = compute_critical_path(
    {"A": "p", "B": "p"},
    {"A": [], "B": ["A"]},
    {"A": 100},
)
ASSERT result.total_duration_ms == 100
```

### File Impacts

#### TS-43-8: Extract File Impacts from Tasks

**Requirement:** 43-REQ-3.1
**Type:** unit
**Description:** Verify file path extraction from tasks.md.

**Preconditions:**
- Fixture spec directory with tasks.md containing:
  ```
  - [ ] 2. Implement feature
    - [ ] 2.1 Update `agent_fox/cli/status.py`
    - [ ] 2.2 Update `agent_fox/engine/engine.py`
  ```

**Input:**
- Call `extract_file_impacts(spec_dir, task_group=2)`.

**Expected:**
- Result contains "agent_fox/cli/status.py" and "agent_fox/engine/engine.py".

**Assertion pseudocode:**
```
files = extract_file_impacts(spec_dir, task_group=2)
ASSERT "agent_fox/cli/status.py" IN files
ASSERT "agent_fox/engine/engine.py" IN files
```

#### TS-43-9: Detect Conflicts Between Tasks

**Requirement:** 43-REQ-3.2
**Type:** unit
**Description:** Verify conflict detection between overlapping file sets.

**Preconditions:**
- Two FileImpact objects:
  - node_a: {"file1.py", "file2.py"}
  - node_b: {"file2.py", "file3.py"}

**Input:**
- Call `detect_conflicts([impact_a, impact_b])`.

**Expected:**
- One conflict: ("node_a", "node_b", {"file2.py"}).

**Assertion pseudocode:**
```
impacts = [
    FileImpact("node_a", {"file1.py", "file2.py"}),
    FileImpact("node_b", {"file2.py", "file3.py"}),
]
conflicts = detect_conflicts(impacts)
ASSERT len(conflicts) == 1
ASSERT conflicts[0] == ("node_a", "node_b", {"file2.py"})
```

#### TS-43-10: Filter Conflicts from Dispatch

**Requirement:** 43-REQ-3.3
**Type:** unit
**Description:** Verify conflicting tasks are excluded from dispatch.

**Preconditions:**
- Three ready tasks: ["a", "b", "c"].
- FileImpacts: a={"x.py"}, b={"x.py", "y.py"}, c={"z.py"}.

**Input:**
- Call `filter_conflicts_from_dispatch(["a", "b", "c"], impacts)`.

**Expected:**
- Result is ["a", "c"] (b excluded due to conflict with a on x.py).

**Assertion pseudocode:**
```
impacts = [
    FileImpact("a", {"x.py"}),
    FileImpact("b", {"x.py", "y.py"}),
    FileImpact("c", {"z.py"}),
]
result = filter_conflicts_from_dispatch(["a", "b", "c"], impacts)
ASSERT result == ["a", "c"]
```

#### TS-43-E5: No File Impacts is Non-Conflicting

**Requirement:** 43-REQ-3.E1
**Type:** unit
**Description:** Verify tasks with empty file sets are always dispatched.

**Preconditions:**
- Two ready tasks, one with files, one without.
- FileImpacts: a={"x.py"}, b=set().

**Input:**
- Call `filter_conflicts_from_dispatch(["a", "b"], impacts)`.

**Expected:**
- Both dispatched: ["a", "b"].

**Assertion pseudocode:**
```
impacts = [
    FileImpact("a", {"x.py"}),
    FileImpact("b", set()),
]
result = filter_conflicts_from_dispatch(["a", "b"], impacts)
ASSERT result == ["a", "b"]
```

#### TS-43-E6: Missing Spec Files

**Requirement:** 43-REQ-3.E2
**Type:** unit
**Description:** Verify extract_file_impacts handles missing files gracefully.

**Preconditions:**
- Empty spec directory (no tasks.md or design.md).

**Input:**
- Call `extract_file_impacts(empty_dir, task_group=1)`.

**Expected:**
- Returns empty set.

**Assertion pseudocode:**
```
files = extract_file_impacts(empty_dir, task_group=1)
ASSERT files == set()
```

### Blocking History

#### TS-43-11: Record Blocking Decision

**Requirement:** 43-REQ-4.1
**Type:** unit
**Description:** Verify blocking decisions are persisted to DuckDB.

**Preconditions:**
- In-memory DuckDB with blocking_history table created.

**Input:**
- Call `record_blocking_decision(conn, decision)` with a BlockingDecision.

**Expected:**
- Row exists in blocking_history with matching fields.

**Assertion pseudocode:**
```
decision = BlockingDecision("spec_a", "skeptic", 3, 2, True, "correct_block")
record_blocking_decision(conn, decision)
rows = conn.execute("SELECT * FROM blocking_history").fetchall()
ASSERT len(rows) == 1
ASSERT rows[0][1] == "spec_a"  # spec_name
ASSERT rows[0][2] == "skeptic"  # archetype
```

#### TS-43-12: Compute Optimal Threshold

**Requirement:** 43-REQ-4.2
**Type:** unit
**Description:** Verify optimal threshold computation with sufficient data.

**Preconditions:**
- 25 blocking decisions for "skeptic" archetype:
  - 15 correct_block with critical_count 3-5
  - 5 correct_pass with critical_count 0-1
  - 5 false_positive with critical_count 2

**Input:**
- Call `compute_optimal_threshold(conn, "skeptic", min_decisions=20)`.

**Expected:**
- Returns an integer threshold (not None).
- Threshold is a value that minimizes false positives while keeping FNR <= 0.1.

**Assertion pseudocode:**
```
threshold = compute_optimal_threshold(conn, "skeptic", min_decisions=20)
ASSERT threshold is not None
ASSERT isinstance(threshold, int)
ASSERT threshold >= 1
```

#### TS-43-13: Insufficient Data Returns None

**Requirement:** 43-REQ-4.3
**Type:** unit
**Description:** Verify None returned when insufficient decisions exist.

**Preconditions:**
- 5 blocking decisions (below min_decisions=20).

**Input:**
- Call `compute_optimal_threshold(conn, "skeptic", min_decisions=20)`.

**Expected:**
- Returns None.

**Assertion pseudocode:**
```
threshold = compute_optimal_threshold(conn, "skeptic", min_decisions=20)
ASSERT threshold is None
```

#### TS-43-14: Store and Retrieve Learned Threshold

**Requirement:** 43-REQ-4.5, 43-REQ-4.6
**Type:** unit
**Description:** Verify store and get operations for learned thresholds.

**Preconditions:**
- In-memory DuckDB with learned_thresholds table.

**Input:**
- Store threshold 3 for "skeptic", then retrieve it.

**Expected:**
- `get_learned_threshold(conn, "skeptic") == 3`.

**Assertion pseudocode:**
```
store_learned_threshold(conn, "skeptic", 3, 0.85, 25)
result = get_learned_threshold(conn, "skeptic")
ASSERT result == 3
```

#### TS-43-15: Format Learned Thresholds

**Requirement:** 43-REQ-4.7
**Type:** unit
**Description:** Verify format output for learned thresholds.

**Preconditions:**
- DuckDB with one learned threshold stored.

**Input:**
- Call `format_learned_thresholds(conn)`.

**Expected:**
- Output contains "== Learned Blocking Thresholds =="
- Output contains archetype name and threshold value.

**Assertion pseudocode:**
```
store_learned_threshold(conn, "skeptic", 3, 0.85, 25)
output = format_learned_thresholds(conn)
ASSERT "== Learned Blocking Thresholds ==" IN output
ASSERT "skeptic" IN output
ASSERT "threshold=3" IN output
```

#### TS-43-E7: Missing Table Returns None

**Requirement:** 43-REQ-4.E1
**Type:** unit
**Description:** Verify compute_optimal_threshold handles missing table.

**Preconditions:**
- DuckDB connection without blocking_history table.

**Input:**
- Call `compute_optimal_threshold(conn, "skeptic")`.

**Expected:**
- Returns None (not raise).

**Assertion pseudocode:**
```
threshold = compute_optimal_threshold(conn, "skeptic")
ASSERT threshold is None
```

#### TS-43-E8: Uniform Outcomes

**Requirement:** 43-REQ-4.E2
**Type:** unit
**Description:** Verify threshold with all-same-outcome history.

**Preconditions:**
- 25 decisions all with outcome "correct_pass".

**Input:**
- Call `compute_optimal_threshold(conn, "skeptic", min_decisions=20)`.

**Expected:**
- Returns an integer threshold (the system computes a valid value even
  when all decisions agree).

**Assertion pseudocode:**
```
threshold = compute_optimal_threshold(conn, "skeptic", min_decisions=20)
ASSERT threshold is not None
ASSERT isinstance(threshold, int)
```

## Property Test Cases

### TS-43-P1: Failure Rate Bounds

**Property:** Property 1 from design.md
**Validates:** 43-REQ-1.1
**Type:** property
**Description:** SpecMetrics failure_rate is always in [0.0, 1.0].

**For any:** SpecMetrics returned by build_project_model
**Invariant:** 0.0 <= failure_rate <= 1.0 and session_count >= 1

**Assertion pseudocode:**
```
FOR ANY spec_metrics IN build_project_model(conn).spec_outcomes.values():
    ASSERT 0.0 <= spec_metrics.failure_rate <= 1.0
    ASSERT spec_metrics.session_count >= 1
```

### TS-43-P2: Critical Path Determinism

**Property:** Property 3 from design.md
**Validates:** 43-REQ-2.1, 43-REQ-2.3
**Type:** property
**Description:** Same inputs always produce same critical path.

**For any:** DAG with nodes, edges, and duration hints
**Invariant:** Two calls with identical inputs yield identical results.

**Assertion pseudocode:**
```
FOR ANY (nodes, edges, durations) IN dag_strategy():
    r1 = compute_critical_path(nodes, edges, durations)
    r2 = compute_critical_path(nodes, edges, durations)
    ASSERT r1.path == r2.path
    ASSERT r1.total_duration_ms == r2.total_duration_ms
    ASSERT r1.tied_paths == r2.tied_paths
```

### TS-43-P3: Conflict Symmetry

**Property:** Property 4 from design.md
**Validates:** 43-REQ-3.2
**Type:** property
**Description:** Each conflict pair appears once with lower node_id first.

**For any:** list of FileImpact objects
**Invariant:** All conflicts have first element < second element alphabetically, no duplicates.

**Assertion pseudocode:**
```
FOR ANY impacts IN file_impact_strategy():
    conflicts = detect_conflicts(impacts)
    FOR (a, b, _) IN conflicts:
        ASSERT a < b
    pairs = [(a, b) FOR (a, b, _) IN conflicts]
    ASSERT len(pairs) == len(set(pairs))
```

### TS-43-P4: Dispatch Safety

**Property:** Property 5 from design.md
**Validates:** 43-REQ-3.3
**Type:** property
**Description:** No two dispatched tasks share predicted files.

**For any:** ready list and file impacts
**Invariant:** Pairwise file set intersection of dispatched tasks is empty.

**Assertion pseudocode:**
```
FOR ANY (ready, impacts) IN dispatch_strategy():
    dispatched = filter_conflicts_from_dispatch(ready, impacts)
    impact_map = {imp.node_id: imp.predicted_files FOR imp IN impacts}
    FOR i IN range(len(dispatched)):
        FOR j IN range(i+1, len(dispatched)):
            files_i = impact_map.get(dispatched[i], set())
            files_j = impact_map.get(dispatched[j], set())
            ASSERT files_i & files_j == set()
```

### TS-43-P5: Critical Path Duration Optimality

**Property:** Property 2 from design.md
**Validates:** 43-REQ-2.1
**Type:** property
**Description:** Critical path duration equals maximum earliest finish.

**For any:** DAG with duration hints
**Invariant:** total_duration_ms equals the independently computed maximum
earliest finish across all nodes.

**Assertion pseudocode:**
```
FOR ANY (nodes, edges, durations) IN dag_strategy():
    result = compute_critical_path(nodes, edges, durations)
    # Independently compute max earliest finish
    ef = forward_pass(nodes, edges, durations)
    ASSERT result.total_duration_ms == max(ef.values(), default=0)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 43-REQ-1.1 | TS-43-1 | unit |
| 43-REQ-1.2 | TS-43-2 | unit |
| 43-REQ-1.3 | TS-43-3 | unit |
| 43-REQ-1.4 | TS-43-4 | unit |
| 43-REQ-1.E1 | TS-43-E1 | unit |
| 43-REQ-1.E2 | TS-43-E2 | unit |
| 43-REQ-2.1 | TS-43-5 | unit |
| 43-REQ-2.2 | TS-43-7 | unit |
| 43-REQ-2.3 | TS-43-6 | unit |
| 43-REQ-2.E1 | TS-43-E3 | unit |
| 43-REQ-2.E2 | TS-43-E4 | unit |
| 43-REQ-3.1 | TS-43-8 | unit |
| 43-REQ-3.2 | TS-43-9 | unit |
| 43-REQ-3.3 | TS-43-10 | unit |
| 43-REQ-3.E1 | TS-43-E5 | unit |
| 43-REQ-3.E2 | TS-43-E6 | unit |
| 43-REQ-4.1 | TS-43-11 | unit |
| 43-REQ-4.2 | TS-43-12 | unit |
| 43-REQ-4.3 | TS-43-13 | unit |
| 43-REQ-4.5 | TS-43-14 | unit |
| 43-REQ-4.6 | TS-43-14 | unit |
| 43-REQ-4.7 | TS-43-15 | unit |
| 43-REQ-4.E1 | TS-43-E7 | unit |
| 43-REQ-4.E2 | TS-43-E8 | unit |
| Property 1 | TS-43-P1 | property |
| Property 2 | TS-43-P5 | property |
| Property 3 | TS-43-P2 | property |
| Property 4 | TS-43-P3 | property |
| Property 5 | TS-43-P4 | property |
