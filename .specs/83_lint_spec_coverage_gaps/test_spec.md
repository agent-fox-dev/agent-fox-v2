# Test Specification: lint-specs Coverage Gaps

## Overview

Tests validate that 6 new lint rules produce correct findings. Unit tests
verify each rule function in isolation; property tests verify invariants
across generated inputs; an integration smoke test verifies end-to-end
wiring through `validate_specs`.

## Test Cases

### TS-83-1: Missing Execution Paths section detected

**Requirement:** 83-REQ-1.1
**Type:** unit
**Description:** Verifies that a design.md without `## Execution Paths` triggers
a `missing-section` finding.

**Preconditions:**
- Spec folder with a `design.md` containing standard sections but no
  `## Execution Paths`.

**Input:**
- design.md content with `## Overview`, `## Architecture`,
  `## Correctness Properties`, `## Error Handling`, `## Definition of Done`
  but no `## Execution Paths`.

**Expected:**
- Finding list contains a finding with `rule="missing-section"`,
  `severity="warning"`, `file="design.md"`, message mentioning
  "Execution Paths".

**Assertion pseudocode:**
```
findings = check_section_schema(spec_name, spec_path)
ep_findings = [f for f in findings if "Execution Paths" in f.message]
ASSERT len(ep_findings) == 1
ASSERT ep_findings[0].severity == "warning"
```

### TS-83-2: Execution Paths section present — no finding

**Requirement:** 83-REQ-1.2
**Type:** unit
**Description:** Verifies that a design.md with `## Execution Paths` produces
no finding for that section.

**Preconditions:**
- Spec folder with a complete `design.md` including `## Execution Paths`.

**Input:**
- design.md with all required sections including `## Execution Paths`.

**Expected:**
- No finding with message mentioning "Execution Paths".

**Assertion pseudocode:**
```
findings = check_section_schema(spec_name, spec_path)
ep_findings = [f for f in findings if "Execution Paths" in f.message]
ASSERT len(ep_findings) == 0
```

### TS-83-3: Missing Integration Smoke Tests section detected

**Requirement:** 83-REQ-2.1
**Type:** unit
**Description:** Verifies that a test_spec.md without
`## Integration Smoke Tests` triggers a `missing-section` finding.

**Preconditions:**
- Spec folder with a `test_spec.md` containing `## Test Cases` and
  `## Coverage Matrix` but no `## Integration Smoke Tests`.

**Input:**
- test_spec.md content with standard sections but no
  `## Integration Smoke Tests`.

**Expected:**
- Finding with `rule="missing-section"`, `severity="warning"`,
  `file="test_spec.md"`, message mentioning "Integration Smoke Tests".

**Assertion pseudocode:**
```
findings = check_section_schema(spec_name, spec_path)
smoke_findings = [f for f in findings if "Integration Smoke Tests" in f.message]
ASSERT len(smoke_findings) == 1
ASSERT smoke_findings[0].severity == "warning"
```

### TS-83-4: Integration Smoke Tests present — no finding

**Requirement:** 83-REQ-2.2
**Type:** unit
**Description:** Verifies that a test_spec.md with
`## Integration Smoke Tests` produces no finding for that section.

**Preconditions:**
- Spec folder with a complete `test_spec.md` including
  `## Integration Smoke Tests`.

**Input:**
- test_spec.md with all required sections including
  `## Integration Smoke Tests`.

**Expected:**
- No finding with message mentioning "Integration Smoke Tests".

**Assertion pseudocode:**
```
findings = check_section_schema(spec_name, spec_path)
smoke_findings = [f for f in findings if "Integration Smoke Tests" in f.message]
ASSERT len(smoke_findings) == 0
```

### TS-83-5: Too many requirements detected

**Requirement:** 83-REQ-3.1
**Type:** unit
**Description:** Verifies that requirements.md with >10 requirements triggers
`too-many-requirements`.

**Preconditions:**
- Spec folder with a `requirements.md` containing 11
  `### Requirement N:` headings.

**Input:**
- requirements.md with headings `### Requirement 1: A` through
  `### Requirement 11: K`.

**Expected:**
- Finding with `rule="too-many-requirements"`, `severity="warning"`,
  `file="requirements.md"`, message stating count 11 and limit 10.

**Assertion pseudocode:**
```
findings = check_too_many_requirements(spec_name, spec_path)
ASSERT len(findings) == 1
ASSERT findings[0].rule == "too-many-requirements"
ASSERT "11" in findings[0].message
```

### TS-83-6: Requirements at or below limit — no finding

**Requirement:** 83-REQ-3.2
**Type:** unit
**Description:** Verifies that requirements.md with exactly 10 requirements
produces no finding.

**Preconditions:**
- Spec folder with a `requirements.md` containing exactly 10
  `### Requirement N:` headings.

**Input:**
- requirements.md with headings `### Requirement 1: A` through
  `### Requirement 10: J`.

**Expected:**
- Empty findings list.

**Assertion pseudocode:**
```
findings = check_too_many_requirements(spec_name, spec_path)
ASSERT len(findings) == 0
```

### TS-83-7: Wrong first group detected

**Requirement:** 83-REQ-4.1
**Type:** unit
**Description:** Verifies that a first task group without "fail" and "test"
keywords triggers `wrong-first-group`.

**Preconditions:**
- Parsed task groups list with first group titled "Implement core module".

**Input:**
- `task_groups = [TaskGroupDef(number=1, title="Implement core module", ...)]`

**Expected:**
- Finding with `rule="wrong-first-group"`, `severity="warning"`.

**Assertion pseudocode:**
```
findings = check_first_group_title(spec_name, task_groups)
ASSERT len(findings) == 1
ASSERT findings[0].rule == "wrong-first-group"
```

### TS-83-8: Correct first group — no finding

**Requirement:** 83-REQ-4.2
**Type:** unit
**Description:** Verifies that a first task group with "failing" and "tests"
produces no finding.

**Preconditions:**
- Parsed task groups list with first group titled
  "Write failing spec tests".

**Input:**
- `task_groups = [TaskGroupDef(number=1, title="Write failing spec tests", ...)]`

**Expected:**
- Empty findings list.

**Assertion pseudocode:**
```
findings = check_first_group_title(spec_name, task_groups)
ASSERT len(findings) == 0
```

### TS-83-9: Wrong last group detected

**Requirement:** 83-REQ-5.1
**Type:** unit
**Description:** Verifies that a last task group without "wiring" and
"verification" triggers `wrong-last-group`.

**Preconditions:**
- Parsed task groups list with last group titled "Final cleanup".

**Input:**
- `task_groups = [TaskGroupDef(number=1, title="...", ...), TaskGroupDef(number=2, title="Final cleanup", ...)]`

**Expected:**
- Finding with `rule="wrong-last-group"`, `severity="warning"`.

**Assertion pseudocode:**
```
findings = check_last_group_title(spec_name, task_groups)
ASSERT len(findings) == 1
ASSERT findings[0].rule == "wrong-last-group"
```

### TS-83-10: Correct last group — no finding

**Requirement:** 83-REQ-5.2
**Type:** unit
**Description:** Verifies that a last task group with "wiring" and
"verification" produces no finding.

**Preconditions:**
- Parsed task groups list with last group titled "Wiring verification".

**Input:**
- `task_groups = [..., TaskGroupDef(number=5, title="Wiring verification", ...)]`

**Expected:**
- Empty findings list.

**Assertion pseudocode:**
```
findings = check_last_group_title(spec_name, task_groups)
ASSERT len(findings) == 0
```

### TS-83-11: Untraced edge case detected

**Requirement:** 83-REQ-6.1
**Type:** unit
**Description:** Verifies that an edge case req not in the Edge Case Tests
section triggers `untraced-edge-case`.

**Preconditions:**
- Spec folder with `requirements.md` containing `[05-REQ-1.E1]` and
  `test_spec.md` with an `## Edge Case Tests` section that does not
  reference `05-REQ-1.E1`.

**Input:**
- requirements.md: `[05-REQ-1.E1] IF input is empty...`
- test_spec.md: `## Edge Case Tests\n(empty section)`

**Expected:**
- Finding with `rule="untraced-edge-case"`, `severity="warning"`,
  message naming `05-REQ-1.E1`.

**Assertion pseudocode:**
```
findings = check_untraced_edge_cases(spec_name, spec_path)
ASSERT len(findings) == 1
ASSERT "05-REQ-1.E1" in findings[0].message
```

### TS-83-12: All edge cases traced — no finding

**Requirement:** 83-REQ-6.2
**Type:** unit
**Description:** Verifies that when all edge case reqs appear in the Edge
Case Tests section, no finding is produced.

**Preconditions:**
- Spec folder with `requirements.md` containing `[05-REQ-1.E1]` and
  `test_spec.md` with `## Edge Case Tests` section referencing
  `05-REQ-1.E1`.

**Input:**
- requirements.md: `[05-REQ-1.E1] IF input is empty...`
- test_spec.md: `## Edge Case Tests\n### TS-05-E1\n**Requirement:** 05-REQ-1.E1`

**Expected:**
- Empty findings list.

**Assertion pseudocode:**
```
findings = check_untraced_edge_cases(spec_name, spec_path)
ASSERT len(findings) == 0
```

## Edge Case Tests

### TS-83-E1: Missing design.md skips Execution Paths check

**Requirement:** 83-REQ-1.E1
**Type:** unit
**Description:** Verifies that a spec without design.md produces no
Execution Paths finding.

**Preconditions:**
- Spec folder without `design.md`.

**Input:**
- Spec path with no `design.md` file.

**Expected:**
- `check_section_schema` returns no findings for design.md.

**Assertion pseudocode:**
```
findings = check_section_schema(spec_name, spec_path)
design_findings = [f for f in findings if f.file == "design.md"]
ASSERT len(design_findings) == 0
```

### TS-83-E2: Missing test_spec.md skips smoke tests check

**Requirement:** 83-REQ-2.E1
**Type:** unit
**Description:** Verifies that a spec without test_spec.md produces no
Integration Smoke Tests finding.

**Preconditions:**
- Spec folder without `test_spec.md`.

**Input:**
- Spec path with no `test_spec.md` file.

**Expected:**
- `check_section_schema` returns no findings for test_spec.md.

**Assertion pseudocode:**
```
findings = check_section_schema(spec_name, spec_path)
ts_findings = [f for f in findings if f.file == "test_spec.md"]
ASSERT len(ts_findings) == 0
```

### TS-83-E3: Missing requirements.md skips count check

**Requirement:** 83-REQ-3.E1
**Type:** unit
**Description:** Verifies that a spec without requirements.md returns no
too-many-requirements finding.

**Preconditions:**
- Spec folder without `requirements.md`.

**Input:**
- Spec path with no `requirements.md` file.

**Expected:**
- Empty findings list.

**Assertion pseudocode:**
```
findings = check_too_many_requirements(spec_name, spec_path)
ASSERT len(findings) == 0
```

### TS-83-E4: Zero task groups skips title checks

**Requirement:** 83-REQ-4.E2, 83-REQ-5.E2
**Type:** unit
**Description:** Verifies that empty task groups list produces no first/last
group findings.

**Preconditions:**
- Empty task groups list.

**Input:**
- `task_groups = []`

**Expected:**
- Both `check_first_group_title` and `check_last_group_title` return
  empty findings lists.

**Assertion pseudocode:**
```
ASSERT check_first_group_title(spec_name, []) == []
ASSERT check_last_group_title(spec_name, []) == []
```

### TS-83-E5: No edge case reqs — no findings

**Requirement:** 83-REQ-6.E2
**Type:** unit
**Description:** Verifies that a spec with no edge case requirements produces
no untraced-edge-case findings.

**Preconditions:**
- Spec with `requirements.md` containing only non-edge-case requirements
  (e.g., `[05-REQ-1.1]`) and a `test_spec.md`.

**Input:**
- requirements.md with only `[05-REQ-1.1]`, no `E` suffix IDs.

**Expected:**
- Empty findings list.

**Assertion pseudocode:**
```
findings = check_untraced_edge_cases(spec_name, spec_path)
ASSERT len(findings) == 0
```

### TS-83-E6: No Edge Case Tests section — all edge cases untraced

**Requirement:** 83-REQ-6.E3
**Type:** unit
**Description:** Verifies that when test_spec.md has no Edge Case Tests
section, all edge case reqs are reported as untraced.

**Preconditions:**
- Spec with `requirements.md` containing 2 edge case IDs and `test_spec.md`
  without an `## Edge Case Tests` section.

**Input:**
- requirements.md: `[05-REQ-1.E1]` and `[05-REQ-2.E1]`
- test_spec.md: only `## Test Cases` and `## Coverage Matrix`

**Expected:**
- 2 findings with `rule="untraced-edge-case"`.

**Assertion pseudocode:**
```
findings = check_untraced_edge_cases(spec_name, spec_path)
ASSERT len(findings) == 2
ASSERT all(f.rule == "untraced-edge-case" for f in findings)
```

## Property Test Cases

### TS-83-P1: Requirement Count Threshold

**Property:** Property 3 from design.md
**Validates:** 83-REQ-3.1, 83-REQ-3.2
**Type:** property
**Description:** For any count of requirements N (0-30), the rule produces
exactly one finding when N > 10 and zero findings otherwise.

**For any:** N in integers(0, 30)
**Invariant:** `len(findings) == (1 if N > 10 else 0)`

**Assertion pseudocode:**
```
FOR ANY n IN integers(0, 30):
    content = generate_requirements_md(n)
    write content to tmp_path / "requirements.md"
    findings = check_too_many_requirements(spec_name, tmp_path)
    ASSERT len(findings) == (1 if n > 10 else 0)
```

### TS-83-P2: First Group Keyword Presence

**Property:** Property 4 from design.md
**Validates:** 83-REQ-4.1, 83-REQ-4.2
**Type:** property
**Description:** A first group produces no finding iff its lowered title
contains both "fail" and "test".

**For any:** title in text(min_size=0, max_size=100)
**Invariant:** `len(findings) == 0 iff ("fail" in title.lower() and "test" in title.lower())`

**Assertion pseudocode:**
```
FOR ANY title IN text(min_size=0, max_size=100):
    groups = [make_group(number=1, title=title)]
    findings = check_first_group_title(spec_name, groups)
    has_keywords = "fail" in title.lower() and "test" in title.lower()
    ASSERT (len(findings) == 0) == has_keywords
```

### TS-83-P3: Last Group Keyword Presence

**Property:** Property 5 from design.md
**Validates:** 83-REQ-5.1, 83-REQ-5.2
**Type:** property
**Description:** The last group produces no finding iff its lowered title
contains both "wiring" and "verification".

**For any:** title in text(min_size=0, max_size=100)
**Invariant:** `len(findings) == 0 iff ("wiring" in title.lower() and "verification" in title.lower())`

**Assertion pseudocode:**
```
FOR ANY title IN text(min_size=0, max_size=100):
    groups = [make_group(number=1, title="Write failing tests"),
              make_group(number=2, title=title)]
    findings = check_last_group_title(spec_name, groups)
    has_keywords = "wiring" in title.lower() and "verification" in title.lower()
    ASSERT (len(findings) == 0) == has_keywords
```

### TS-83-P4: Edge Case Traceability Count

**Property:** Property 6 from design.md
**Validates:** 83-REQ-6.1, 83-REQ-6.2
**Type:** property
**Description:** The number of untraced-edge-case findings equals the number
of edge case req IDs not present in the Edge Case Tests section.

**For any:** edge_case_ids in sets(text matching NN-REQ-X.EN pattern,
min_size=0, max_size=5), traced_subset in subsets of edge_case_ids
**Invariant:** `len(findings) == len(edge_case_ids) - len(traced_subset)`

**Assertion pseudocode:**
```
FOR ANY (all_ids, traced_ids) IN edge_case_id_pairs(max_size=5):
    write requirements.md with all_ids
    write test_spec.md with Edge Case Tests section referencing traced_ids
    findings = check_untraced_edge_cases(spec_name, spec_path)
    ASSERT len(findings) == len(all_ids) - len(traced_ids)
```

## Integration Smoke Tests

### TS-83-SMOKE-1: All new rules fire on deficient spec

**Execution Path:** Paths 1-4 from design.md
**Description:** Verifies that `validate_specs` produces findings from all
6 new rules when run against a spec that violates all of them.

**Setup:** Create a fixture spec folder in `tmp_path` with:
- `prd.md` (minimal)
- `requirements.md` with 11 requirements and 1 edge case req
- `design.md` without `## Execution Paths`
- `test_spec.md` without `## Integration Smoke Tests` and without
  `## Edge Case Tests`
- `tasks.md` with first group "Implement module" and last group "Cleanup"

**Trigger:** `validate_specs(tmp_path, [SpecInfo(name="83_test", path=...)])`

**Expected side effects:**
- Findings list contains at least one finding with each of:
  - `rule="missing-section"` and `"Execution Paths"` in message
  - `rule="missing-section"` and `"Integration Smoke Tests"` in message
  - `rule="too-many-requirements"`
  - `rule="wrong-first-group"`
  - `rule="wrong-last-group"`
  - `rule="untraced-edge-case"`

**Must NOT satisfy with:** Mocking any validator function — all real
validator code must execute.

**Assertion pseudocode:**
```
specs = [SpecInfo(name="83_test", path=fixture_path)]
findings = validate_specs(tmp_path, specs)
rules = {f.rule for f in findings}
messages = " ".join(f.message for f in findings)
ASSERT "missing-section" in rules
ASSERT "Execution Paths" in messages
ASSERT "Integration Smoke Tests" in messages
ASSERT "too-many-requirements" in rules
ASSERT "wrong-first-group" in rules
ASSERT "wrong-last-group" in rules
ASSERT "untraced-edge-case" in rules
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 83-REQ-1.1 | TS-83-1 | unit |
| 83-REQ-1.2 | TS-83-2 | unit |
| 83-REQ-1.E1 | TS-83-E1 | unit |
| 83-REQ-2.1 | TS-83-3 | unit |
| 83-REQ-2.2 | TS-83-4 | unit |
| 83-REQ-2.E1 | TS-83-E2 | unit |
| 83-REQ-3.1 | TS-83-5 | unit |
| 83-REQ-3.2 | TS-83-6 | unit |
| 83-REQ-3.E1 | TS-83-E3 | unit |
| 83-REQ-3.E2 | TS-83-6 | unit |
| 83-REQ-4.1 | TS-83-7 | unit |
| 83-REQ-4.2 | TS-83-8 | unit |
| 83-REQ-4.E1 | TS-83-E4 | unit |
| 83-REQ-4.E2 | TS-83-E4 | unit |
| 83-REQ-5.1 | TS-83-9 | unit |
| 83-REQ-5.2 | TS-83-10 | unit |
| 83-REQ-5.E1 | TS-83-E4 | unit |
| 83-REQ-5.E2 | TS-83-E4 | unit |
| 83-REQ-6.1 | TS-83-11 | unit |
| 83-REQ-6.2 | TS-83-12 | unit |
| 83-REQ-6.E1 | TS-83-E5 | unit |
| 83-REQ-6.E2 | TS-83-E5 | unit |
| 83-REQ-6.E3 | TS-83-E6 | unit |
| Property 1 | TS-83-1, TS-83-2 | unit |
| Property 2 | TS-83-3, TS-83-4 | unit |
| Property 3 | TS-83-P1 | property |
| Property 4 | TS-83-P2 | property |
| Property 5 | TS-83-P3 | property |
| Property 6 | TS-83-P4 | property |
