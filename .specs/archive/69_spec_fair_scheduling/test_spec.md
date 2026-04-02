# Test Specification: Spec-Fair Task Scheduling

## Overview

Tests validate that `ready_tasks()` produces spec-fair round-robin ordering
across multiple specs while preserving within-spec ordering (alphabetical or
duration-based). All tests target `GraphSync.ready_tasks()` and/or the
`_interleave_by_spec()` helper function in `graph_sync.py`.

## Test Cases

### TS-69-1: Multi-Spec Round-Robin Ordering

**Requirement:** 69-REQ-1.1
**Type:** unit
**Description:** Verify that tasks from multiple specs are interleaved
round-robin rather than sorted alphabetically.

**Preconditions:**
- Three specs with ready tasks: `65_foo:1`, `67_bar:1`, `68_baz:1`
- All have no predecessors (root nodes)

**Input:**
- `ready = ["65_foo:1", "67_bar:1", "67_bar:2", "68_baz:1"]`

**Expected:**
- `["65_foo:1", "67_bar:1", "68_baz:1", "67_bar:2"]`

**Assertion pseudocode:**
```
result = _interleave_by_spec(["65_foo:1", "67_bar:1", "67_bar:2", "68_baz:1"])
ASSERT result == ["65_foo:1", "67_bar:1", "68_baz:1", "67_bar:2"]
```

### TS-69-2: Spec Number Ascending Order

**Requirement:** 69-REQ-1.2
**Type:** unit
**Description:** Verify specs are ordered by numeric prefix ascending within
each round.

**Preconditions:**
- Two specs: `68_later` and `65_earlier`, each with one ready task

**Input:**
- `ready = ["68_later:1", "65_earlier:1"]`

**Expected:**
- `["65_earlier:1", "68_later:1"]` (65 before 68)

**Assertion pseudocode:**
```
result = _interleave_by_spec(["68_later:1", "65_earlier:1"])
ASSERT result == ["65_earlier:1", "68_later:1"]
```

### TS-69-3: Single-Spec Alphabetical

**Requirement:** 69-REQ-1.3
**Type:** unit
**Description:** Verify single-spec ready tasks are sorted alphabetically.

**Preconditions:**
- One spec with multiple ready tasks

**Input:**
- `ready = ["42_spec:3", "42_spec:1", "42_spec:2"]`

**Expected:**
- `["42_spec:1", "42_spec:2", "42_spec:3"]`

**Assertion pseudocode:**
```
result = _interleave_by_spec(["42_spec:3", "42_spec:1", "42_spec:2"])
ASSERT result == ["42_spec:1", "42_spec:2", "42_spec:3"]
```

### TS-69-4: Non-Numeric Spec Prefix Sorts Last

**Requirement:** 69-REQ-1.4
**Type:** unit
**Description:** Verify specs without numeric prefixes sort after numbered
specs.

**Preconditions:**
- One numbered spec and one non-numbered spec

**Input:**
- `ready = ["no_number:1", "05_numbered:1"]`

**Expected:**
- `["05_numbered:1", "no_number:1"]`

**Assertion pseudocode:**
```
result = _interleave_by_spec(["no_number:1", "05_numbered:1"])
ASSERT result == ["05_numbered:1", "no_number:1"]
```

### TS-69-5: Duration Hints Within Spec Group

**Requirement:** 69-REQ-2.1
**Type:** unit
**Description:** Verify duration hints order tasks within each spec group by
duration descending.

**Preconditions:**
- One spec with three tasks, duration hints provided

**Input:**
- `ready = ["42_spec:1", "42_spec:2", "42_spec:3"]`
- `duration_hints = {"42_spec:1": 100, "42_spec:2": 500, "42_spec:3": 300}`

**Expected:**
- `["42_spec:2", "42_spec:3", "42_spec:1"]` (500, 300, 100)

**Assertion pseudocode:**
```
result = _interleave_by_spec(
    ["42_spec:1", "42_spec:2", "42_spec:3"],
    duration_hints={"42_spec:1": 100, "42_spec:2": 500, "42_spec:3": 300},
)
ASSERT result == ["42_spec:2", "42_spec:3", "42_spec:1"]
```

### TS-69-6: Duration Hints Do Not Override Cross-Spec Fairness

**Requirement:** 69-REQ-2.2
**Type:** unit
**Description:** Verify that a very long task from a later spec does not jump
ahead of an earlier spec's slot.

**Preconditions:**
- Two specs; later spec has a much longer predicted duration

**Input:**
- `ready = ["10_fast:1", "20_slow:1"]`
- `duration_hints = {"10_fast:1": 100, "20_slow:1": 99999}`

**Expected:**
- `["10_fast:1", "20_slow:1"]` (spec 10 first despite shorter duration)

**Assertion pseudocode:**
```
result = _interleave_by_spec(
    ["10_fast:1", "20_slow:1"],
    duration_hints={"10_fast:1": 100, "20_slow:1": 99999},
)
ASSERT result[0] == "10_fast:1"
ASSERT result[1] == "20_slow:1"
```

### TS-69-7: Duration Hints Partial Coverage Within Spec

**Requirement:** 69-REQ-2.3
**Type:** unit
**Description:** Verify hinted tasks come before unhinted tasks within a spec
group.

**Preconditions:**
- One spec, three tasks, only two have duration hints

**Input:**
- `ready = ["42_spec:1", "42_spec:2", "42_spec:3"]`
- `duration_hints = {"42_spec:1": 200, "42_spec:3": 500}`

**Expected:**
- `["42_spec:3", "42_spec:1", "42_spec:2"]` (hinted descending, then unhinted)

**Assertion pseudocode:**
```
result = _interleave_by_spec(
    ["42_spec:1", "42_spec:2", "42_spec:3"],
    duration_hints={"42_spec:1": 200, "42_spec:3": 500},
)
ASSERT result == ["42_spec:3", "42_spec:1", "42_spec:2"]
```

### TS-69-8: Spec Name Extraction Simple

**Requirement:** 69-REQ-3.1
**Type:** unit
**Description:** Verify spec name is extracted as everything before the first
colon.

**Preconditions:** None

**Input:**
- `node_id = "67_quality_gate:2"`

**Expected:**
- spec name = `"67_quality_gate"`

**Assertion pseudocode:**
```
ASSERT _spec_name("67_quality_gate:2") == "67_quality_gate"
```

### TS-69-9: Spec Name Extraction Multi-Colon

**Requirement:** 69-REQ-3.2
**Type:** unit
**Description:** Verify only the first colon is used for splitting.

**Preconditions:** None

**Input:**
- `node_id = "67_quality_gate:1:auditor"`

**Expected:**
- spec name = `"67_quality_gate"`

**Assertion pseudocode:**
```
ASSERT _spec_name("67_quality_gate:1:auditor") == "67_quality_gate"
```

### TS-69-10: Ready Tasks Integration

**Requirement:** 69-REQ-1.1, 69-REQ-2.2
**Type:** unit
**Description:** Verify `GraphSync.ready_tasks()` returns spec-fair ordering
in a realistic multi-spec graph.

**Preconditions:**
- GraphSync with nodes from two independent specs, both root nodes pending

**Input:**
- Nodes: `{"67_qg:0": "pending", "68_cfg:0": "pending"}`, no edges

**Expected:**
- `["67_qg:0", "68_cfg:0"]` (both present, spec 67 first by number)

**Assertion pseudocode:**
```
gs = GraphSync({"67_qg:0": "pending", "68_cfg:0": "pending"}, {})
result = gs.ready_tasks()
ASSERT result == ["67_qg:0", "68_cfg:0"]
```

## Edge Case Tests

### TS-69-E1: Single-Spec Identity

**Requirement:** 69-REQ-1.E1
**Type:** unit
**Description:** Verify single-spec behavior matches alphabetical sort.

**Preconditions:**
- All tasks from one spec

**Input:**
- `ready = ["42_spec:3", "42_spec:1", "42_spec:0"]`

**Expected:**
- `["42_spec:0", "42_spec:1", "42_spec:3"]`

**Assertion pseudocode:**
```
result = _interleave_by_spec(["42_spec:3", "42_spec:1", "42_spec:0"])
ASSERT result == sorted(["42_spec:3", "42_spec:1", "42_spec:0"])
```

### TS-69-E2: Empty List

**Requirement:** 69-REQ-1.E2
**Type:** unit
**Description:** Verify empty input returns empty output.

**Preconditions:** None

**Input:**
- `ready = []`

**Expected:**
- `[]`

**Assertion pseudocode:**
```
ASSERT _interleave_by_spec([]) == []
```

### TS-69-E3: Duration Hints Single Spec

**Requirement:** 69-REQ-2.E1
**Type:** unit
**Description:** Verify duration ordering within a single spec.

**Preconditions:**
- One spec, duration hints provided

**Input:**
- `ready = ["42_spec:1", "42_spec:2"]`
- `duration_hints = {"42_spec:1": 100, "42_spec:2": 500}`

**Expected:**
- `["42_spec:2", "42_spec:1"]` (duration descending)

**Assertion pseudocode:**
```
result = _interleave_by_spec(
    ["42_spec:1", "42_spec:2"],
    duration_hints={"42_spec:1": 100, "42_spec:2": 500},
)
ASSERT result == ["42_spec:2", "42_spec:1"]
```

### TS-69-E4: No-Colon Node ID

**Requirement:** 69-REQ-3.E1
**Type:** unit
**Description:** Verify node ID with no colon uses full ID as spec name.

**Preconditions:** None

**Input:**
- `node_id = "orphan_node"`

**Expected:**
- spec name = `"orphan_node"`

**Assertion pseudocode:**
```
ASSERT _spec_name("orphan_node") == "orphan_node"
```

## Property Test Cases

### TS-69-P1: Fairness Guarantee

**Property:** Property 1 from design.md
**Validates:** 69-REQ-1.1, 69-REQ-1.2
**Type:** property
**Description:** For any multi-spec ready set, every spec's first task appears
within the first N positions (where N = number of distinct specs).

**For any:** list of 2-50 node IDs across 2-10 specs (generated with
Hypothesis)
**Invariant:** For each spec with at least one task, its first task appears at
index < total_spec_count in the result.

**Assertion pseudocode:**
```
FOR ANY ready IN lists(spec_node_ids, min_size=2, max_size=50):
    result = _interleave_by_spec(ready)
    specs = unique_specs(ready)
    FOR EACH spec IN specs:
        first_index = index of first task from spec in result
        ASSERT first_index < len(specs)
```

### TS-69-P2: Single-Spec Identity

**Property:** Property 2 from design.md
**Validates:** 69-REQ-1.3, 69-REQ-1.E1
**Type:** property
**Description:** When all tasks belong to one spec, result equals sorted(input).

**For any:** list of 1-20 node IDs all with the same spec prefix
**Invariant:** `_interleave_by_spec(ready) == sorted(ready)`

**Assertion pseudocode:**
```
FOR ANY ready IN single_spec_lists(min_size=1, max_size=20):
    ASSERT _interleave_by_spec(ready) == sorted(ready)
```

### TS-69-P3: Duration Preserves Within-Spec Order

**Property:** Property 3 from design.md
**Validates:** 69-REQ-2.1, 69-REQ-2.2
**Type:** property
**Description:** Projecting the interleaved result onto a single spec preserves
duration-descending order.

**For any:** list of node IDs with duration hints across 1-5 specs
**Invariant:** For each spec, the subsequence of its tasks in the result is
ordered by duration descending.

**Assertion pseudocode:**
```
FOR ANY (ready, hints) IN spec_lists_with_hints():
    result = _interleave_by_spec(ready, duration_hints=hints)
    FOR EACH spec IN unique_specs(ready):
        spec_tasks = [t for t in result if _spec_name(t) == spec]
        durations = [hints.get(t, -1) for t in spec_tasks]
        hinted = [d for d in durations if d >= 0]
        ASSERT hinted == sorted(hinted, reverse=True)
```

### TS-69-P4: Completeness

**Property:** Property 4 from design.md
**Validates:** 69-REQ-1.1
**Type:** property
**Description:** The interleaved result is a permutation of the input.

**For any:** list of 0-50 node IDs
**Invariant:** `sorted(result) == sorted(input)`

**Assertion pseudocode:**
```
FOR ANY ready IN lists(spec_node_ids, max_size=50):
    result = _interleave_by_spec(ready)
    ASSERT sorted(result) == sorted(ready)
```

### TS-69-P5: Spec Order Consistency

**Property:** Property 5 from design.md
**Validates:** 69-REQ-1.2, 69-REQ-1.4
**Type:** property
**Description:** Specs with lower numbers always have their first task appear
before specs with higher numbers.

**For any:** list of node IDs across 2-10 specs with numeric prefixes
**Invariant:** For any two specs A, B where A's number < B's number, the first
occurrence of A's task precedes the first occurrence of B's task.

**Assertion pseudocode:**
```
FOR ANY ready IN multi_spec_lists(min_specs=2, max_specs=10):
    result = _interleave_by_spec(ready)
    specs_sorted = sorted(unique_specs(ready), key=_spec_number)
    first_indices = {s: first_index_of(s, result) for s in specs_sorted}
    FOR i, j IN pairs(specs_sorted):
        ASSERT first_indices[specs_sorted[i]] < first_indices[specs_sorted[j]]
```

### TS-69-P6: Empty Stability

**Property:** Property 6 from design.md
**Validates:** 69-REQ-1.E2
**Type:** property
**Description:** Empty input always produces empty output.

**For any:** (trivial — empty list)
**Invariant:** `_interleave_by_spec([]) == []`

**Assertion pseudocode:**
```
ASSERT _interleave_by_spec([]) == []
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 69-REQ-1.1 | TS-69-1, TS-69-10 | unit |
| 69-REQ-1.2 | TS-69-2 | unit |
| 69-REQ-1.3 | TS-69-3 | unit |
| 69-REQ-1.4 | TS-69-4 | unit |
| 69-REQ-1.E1 | TS-69-E1 | unit |
| 69-REQ-1.E2 | TS-69-E2 | unit |
| 69-REQ-2.1 | TS-69-5 | unit |
| 69-REQ-2.2 | TS-69-6 | unit |
| 69-REQ-2.3 | TS-69-7 | unit |
| 69-REQ-2.E1 | TS-69-E3 | unit |
| 69-REQ-3.1 | TS-69-8 | unit |
| 69-REQ-3.2 | TS-69-9 | unit |
| 69-REQ-3.E1 | TS-69-E4 | unit |
| Property 1 | TS-69-P1 | property |
| Property 2 | TS-69-P2 | property |
| Property 3 | TS-69-P3 | property |
| Property 4 | TS-69-P4 | property |
| Property 5 | TS-69-P5 | property |
| Property 6 | TS-69-P6 | property |
