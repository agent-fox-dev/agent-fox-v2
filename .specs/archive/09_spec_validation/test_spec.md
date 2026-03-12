# Test Specification: Specification Validation

## Overview

Tests for the specification validation system: static validation rules, AI
semantic analysis, output formatting, and the `agent-fox lint-spec` CLI
command. Tests map to requirements in `requirements.md` and correctness
properties in `design.md`.

All static rule tests use fixture spec directories under
`tests/fixtures/specs/` with deliberately planted problems for deterministic,
repeatable testing.

## Test Cases

### TS-09-1: Missing files detected

**Requirement:** 09-REQ-2.1, 09-REQ-2.2
**Type:** unit
**Description:** Verify `check_missing_files` produces an Error finding for
each missing expected file.

**Preconditions:**
- Fixture spec directory `tests/fixtures/specs/incomplete_spec/` exists with
  only `prd.md` and `tasks.md` (missing `requirements.md`, `design.md`,
  `test_spec.md`).

**Input:**
- `check_missing_files("incomplete_spec", Path("tests/fixtures/specs/incomplete_spec/"))`

**Expected:**
- Returns exactly 3 findings.
- All findings have severity `"error"`.
- All findings have rule `"missing-file"`.
- Finding messages reference the missing filenames.

**Assertion pseudocode:**
```
findings = check_missing_files("incomplete_spec", fixture_path)
ASSERT len(findings) == 3
FOR EACH f IN findings:
    ASSERT f.severity == "error"
    ASSERT f.rule == "missing-file"
ASSERT {"requirements.md", "design.md", "test_spec.md"} == {f.file for f in findings}
```

---

### TS-09-2: All files present produces no findings

**Requirement:** 09-REQ-2.1
**Type:** unit
**Description:** Verify `check_missing_files` returns an empty list when all
five expected files are present.

**Preconditions:**
- Fixture spec directory `tests/fixtures/specs/complete_spec/` exists with all
  five files.

**Input:**
- `check_missing_files("complete_spec", Path("tests/fixtures/specs/complete_spec/"))`

**Expected:**
- Returns an empty list.

**Assertion pseudocode:**
```
findings = check_missing_files("complete_spec", fixture_path)
ASSERT len(findings) == 0
```

---

### TS-09-3: Oversized task group detected

**Requirement:** 09-REQ-3.1, 09-REQ-3.2
**Type:** unit
**Description:** Verify `check_oversized_groups` flags a task group with more
than 6 subtasks.

**Preconditions:**
- A `TaskGroup` object with 8 subtasks (none are verification steps).

**Input:**
- `check_oversized_groups("test_spec", [task_group_with_8_subtasks])`

**Expected:**
- Returns exactly 1 finding.
- Finding has severity `"warning"` and rule `"oversized-group"`.
- Finding message mentions the group number and subtask count.

**Assertion pseudocode:**
```
group = TaskGroup(number=1, title="Big group", optional=False, subtasks=make_subtasks(8), body="")
findings = check_oversized_groups("test_spec", [group])
ASSERT len(findings) == 1
ASSERT findings[0].severity == "warning"
ASSERT findings[0].rule == "oversized-group"
ASSERT "8" IN findings[0].message
```

---

### TS-09-4: Task group with 6 subtasks is acceptable

**Requirement:** 09-REQ-3.1, 09-REQ-3.2
**Type:** unit
**Description:** Verify `check_oversized_groups` does not flag a task group
with exactly 6 subtasks.

**Preconditions:**
- A `TaskGroup` object with exactly 6 subtasks.

**Input:**
- `check_oversized_groups("test_spec", [task_group_with_6_subtasks])`

**Expected:**
- Returns an empty list.

**Assertion pseudocode:**
```
group = TaskGroup(number=1, title="Okay group", optional=False, subtasks=make_subtasks(6), body="")
findings = check_oversized_groups("test_spec", [group])
ASSERT len(findings) == 0
```

---

### TS-09-5: Verification step excludes from subtask count

**Requirement:** 09-REQ-3.1
**Type:** unit
**Description:** Verify that verification steps (N.V) are excluded from the
subtask count when checking group size.

**Preconditions:**
- A `TaskGroup` with 7 subtasks, one of which is a verification step (1.V).

**Input:**
- `check_oversized_groups("test_spec", [group])`

**Expected:**
- Returns an empty list (6 non-verification subtasks is within the limit).

**Assertion pseudocode:**
```
subtasks = make_subtasks(6) + [Subtask(label="1.V Verify task group 1", checked=False)]
group = TaskGroup(number=1, title="With verify", optional=False, subtasks=subtasks, body="")
findings = check_oversized_groups("test_spec", [group])
ASSERT len(findings) == 0
```

---

### TS-09-6: Missing verification step detected

**Requirement:** 09-REQ-4.1, 09-REQ-4.2
**Type:** unit
**Description:** Verify `check_missing_verification` flags a task group
without a verification step.

**Preconditions:**
- A `TaskGroup` with subtasks but no verification step (no N.V label).

**Input:**
- `check_missing_verification("test_spec", [group_without_verify])`

**Expected:**
- Returns exactly 1 finding.
- Finding has severity `"warning"` and rule `"missing-verification"`.

**Assertion pseudocode:**
```
group = TaskGroup(number=2, title="No verify", optional=False, subtasks=make_subtasks(3), body="")
findings = check_missing_verification("test_spec", [group])
ASSERT len(findings) == 1
ASSERT findings[0].severity == "warning"
ASSERT findings[0].rule == "missing-verification"
```

---

### TS-09-7: Present verification step produces no finding

**Requirement:** 09-REQ-4.1
**Type:** unit
**Description:** Verify `check_missing_verification` returns empty when a
verification step exists.

**Preconditions:**
- A `TaskGroup` with subtasks including a verification step (2.V).

**Input:**
- `check_missing_verification("test_spec", [group_with_verify])`

**Expected:**
- Returns an empty list.

**Assertion pseudocode:**
```
subtasks = make_subtasks(3) + [Subtask(label="2.V Verify task group 2", checked=False)]
group = TaskGroup(number=2, title="With verify", optional=False, subtasks=subtasks, body="")
findings = check_missing_verification("test_spec", [group])
ASSERT len(findings) == 0
```

---

### TS-09-8: Missing acceptance criteria detected

**Requirement:** 09-REQ-5.1, 09-REQ-5.2
**Type:** unit
**Description:** Verify `check_missing_acceptance_criteria` flags requirement
sections without any criteria.

**Preconditions:**
- Fixture spec directory with a `requirements.md` that has a requirement
  heading "### Requirement 3: Empty Req" followed by text but no line
  containing a `[NN-REQ-N.N]` pattern before the next heading.

**Input:**
- `check_missing_acceptance_criteria("test_spec", fixture_path)`

**Expected:**
- Returns at least 1 finding for the empty requirement.
- Finding has severity `"error"` and rule `"missing-acceptance-criteria"`.
- Finding message references "Requirement 3".

**Assertion pseudocode:**
```
findings = check_missing_acceptance_criteria("test_spec", fixture_path)
empty_req_findings = [f for f in findings if "Requirement 3" in f.message]
ASSERT len(empty_req_findings) == 1
ASSERT empty_req_findings[0].severity == "error"
```

---

### TS-09-9: Broken dependency to non-existent spec

**Requirement:** 09-REQ-6.1, 09-REQ-6.2
**Type:** unit
**Description:** Verify `check_broken_dependencies` flags a reference to a
spec that does not exist.

**Preconditions:**
- Fixture spec with a `prd.md` dependency table referencing spec
  `99_nonexistent`.
- `known_specs` dict does not contain `99_nonexistent`.

**Input:**
- `check_broken_dependencies("test_spec", fixture_path, known_specs)`

**Expected:**
- Returns at least 1 Error finding for the missing spec reference.
- Finding has rule `"broken-dependency"`.

**Assertion pseudocode:**
```
known_specs = {"01_core_foundation": [1, 2, 3]}
findings = check_broken_dependencies("test_spec", fixture_path, known_specs)
broken = [f for f in findings if f.rule == "broken-dependency"]
ASSERT len(broken) >= 1
ASSERT broken[0].severity == "error"
ASSERT "99_nonexistent" IN broken[0].message
```

---

### TS-09-10: Broken dependency to non-existent task group

**Requirement:** 09-REQ-6.3
**Type:** unit
**Description:** Verify `check_broken_dependencies` flags a reference to a
task group number that does not exist in the target spec.

**Preconditions:**
- Fixture spec with a `prd.md` dependency table referencing group 99 in
  `01_core_foundation`.
- `known_specs` contains `01_core_foundation` with groups [1, 2, 3, 4, 5].

**Input:**
- `check_broken_dependencies("test_spec", fixture_path, known_specs)`

**Expected:**
- Returns at least 1 Error finding for the missing group.
- Finding message references group 99.

**Assertion pseudocode:**
```
known_specs = {"01_core_foundation": [1, 2, 3, 4, 5]}
findings = check_broken_dependencies("test_spec", fixture_path, known_specs)
group_findings = [f for f in findings if "99" in f.message]
ASSERT len(group_findings) >= 1
ASSERT group_findings[0].severity == "error"
```

---

### TS-09-11: Untraced requirement detected

**Requirement:** 09-REQ-7.1, 09-REQ-7.2
**Type:** unit
**Description:** Verify `check_untraced_requirements` flags requirements not
referenced in test_spec.md.

**Preconditions:**
- Fixture spec with `requirements.md` containing IDs `[09-REQ-1.1]`,
  `[09-REQ-1.2]`, `[09-REQ-2.1]` and `test_spec.md` referencing only
  `09-REQ-1.1` and `09-REQ-2.1`.

**Input:**
- `check_untraced_requirements("test_spec", fixture_path)`

**Expected:**
- Returns exactly 1 Warning finding for `09-REQ-1.2`.
- Finding has rule `"untraced-requirement"`.

**Assertion pseudocode:**
```
findings = check_untraced_requirements("test_spec", fixture_path)
ASSERT len(findings) == 1
ASSERT findings[0].severity == "warning"
ASSERT "09-REQ-1.2" IN findings[0].message
```

---

### TS-09-12: Findings sorted correctly

**Requirement:** 09-REQ-1.3
**Type:** unit
**Description:** Verify findings are sorted by spec name, then file, then
severity (error, warning, hint).

**Preconditions:**
- A list of Finding objects with mixed specs, files, and severities.

**Input:**
- Unsorted list of findings.

**Expected:**
- After sorting, findings are ordered by spec_name (ascending), then file
  (ascending), then severity (error < warning < hint).

**Assertion pseudocode:**
```
findings = [
    Finding("b_spec", "tasks.md", "rule", "hint", "msg", None),
    Finding("a_spec", "tasks.md", "rule", "warning", "msg", None),
    Finding("a_spec", "prd.md", "rule", "error", "msg", None),
    Finding("a_spec", "tasks.md", "rule", "error", "msg", None),
]
sorted_findings = sort_findings(findings)
ASSERT sorted_findings[0].spec_name == "a_spec"
ASSERT sorted_findings[0].file == "prd.md"
ASSERT sorted_findings[1].spec_name == "a_spec"
ASSERT sorted_findings[1].file == "tasks.md"
ASSERT sorted_findings[1].severity == "error"
ASSERT sorted_findings[2].severity == "warning"
ASSERT sorted_findings[3].spec_name == "b_spec"
```

## Property Test Cases

### TS-09-P1: Error findings imply non-zero exit

**Property:** Property 3 from design.md
**Validates:** 09-REQ-9.4
**Type:** property
**Description:** Any findings list with at least one Error produces exit
code 1.

**For any:** non-empty list of Finding objects containing at least one with
severity `"error"`
**Invariant:** CLI invocation with these findings exits with code 1.

**Assertion pseudocode:**
```
FOR ANY findings IN lists_with_at_least_one_error():
    exit_code = compute_exit_code(findings)
    ASSERT exit_code == 1
```

---

### TS-09-P2: No errors implies zero exit

**Property:** Property 4 from design.md
**Validates:** 09-REQ-9.5
**Type:** property
**Description:** A findings list with no Error-severity findings produces exit
code 0.

**For any:** list of Finding objects where all severities are `"warning"` or
`"hint"` (including empty list)
**Invariant:** CLI invocation with these findings exits with code 0.

**Assertion pseudocode:**
```
FOR ANY findings IN lists_without_errors():
    exit_code = compute_exit_code(findings)
    ASSERT exit_code == 0
```

---

### TS-09-P3: Missing files count matches reality

**Property:** Property 5 from design.md
**Validates:** 09-REQ-2.1, 09-REQ-2.2
**Type:** property
**Description:** The number of findings from `check_missing_files` equals the
number of actually missing files (out of the 5 expected).

**For any:** subset S of the 5 expected files that are present in a temp dir
**Invariant:** `len(check_missing_files(...)) == 5 - len(S)`

**Assertion pseudocode:**
```
FOR ANY present_files IN subsets(EXPECTED_FILES):
    create_temp_spec_dir(present_files)
    findings = check_missing_files("test", temp_dir)
    ASSERT len(findings) == 5 - len(present_files)
```

---

### TS-09-P4: Oversized group threshold is exact

**Property:** Property 6 from design.md
**Validates:** 09-REQ-3.1, 09-REQ-3.2
**Type:** property
**Description:** A task group produces a warning if and only if its
non-verification subtask count exceeds 6.

**For any:** integer N in [0, 20] representing the number of non-verification
subtasks
**Invariant:** `len(findings) == 1` iff `N > 6`, else `len(findings) == 0`

**Assertion pseudocode:**
```
FOR ANY n IN integers(0, 20):
    group = make_task_group_with_n_subtasks(n)
    findings = check_oversized_groups("test", [group])
    IF n > 6:
        ASSERT len(findings) == 1
    ELSE:
        ASSERT len(findings) == 0
```

---

### TS-09-P5: Finding immutability

**Property:** Property 1 from design.md
**Validates:** Data integrity
**Type:** property
**Description:** Finding instances are frozen and cannot be mutated.

**For any:** valid Finding instance
**Invariant:** Attempting to set any attribute raises `FrozenInstanceError`.

**Assertion pseudocode:**
```
FOR ANY finding IN valid_findings():
    ASSERT_RAISES FrozenInstanceError FROM (finding.severity = "error")
    ASSERT_RAISES FrozenInstanceError FROM (finding.message = "changed")
```

## Edge Case Tests

### TS-09-E1: No specs directory

**Requirement:** 09-REQ-1.E1
**Type:** integration
**Description:** Verify lint-spec reports an error when `.specs/` does not
exist.

**Preconditions:**
- Working directory has no `.specs/` directory.

**Input:**
- CLI invocation: `["lint-spec"]`

**Expected:**
- Exit code 1.
- Output contains a finding about no specifications found.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["lint-spec"])
ASSERT result.exit_code == 1
ASSERT "no specifications" IN result.output.lower() OR "error" IN result.output.lower()
```

---

### TS-09-E2: Empty specs directory

**Requirement:** 09-REQ-1.E1
**Type:** integration
**Description:** Verify lint-spec reports an error when `.specs/` exists but
contains no spec folders.

**Preconditions:**
- `.specs/` directory exists but is empty (or contains only non-spec files).

**Input:**
- CLI invocation: `["lint-spec"]`

**Expected:**
- Exit code 1.

**Assertion pseudocode:**
```
Path(".specs").mkdir()
result = cli_runner.invoke(main, ["lint-spec"])
ASSERT result.exit_code == 1
```

---

### TS-09-E3: AI unavailable graceful fallback

**Requirement:** 09-REQ-8.E1
**Type:** unit
**Description:** Verify AI validation is skipped gracefully when the model is
unavailable.

**Preconditions:**
- Anthropic client raises an authentication error.

**Input:**
- `run_ai_validation(specs, model="STANDARD")` with mocked client that raises.

**Expected:**
- Returns an empty list (no findings, no exception).
- A warning is logged.

**Assertion pseudocode:**
```
with mock_anthropic_error(AuthenticationError):
    findings = await run_ai_validation(specs, "STANDARD")
    ASSERT len(findings) == 0
    ASSERT warning_was_logged()
```

---

### TS-09-E4: JSON output format

**Requirement:** 09-REQ-9.1, 09-REQ-9.3
**Type:** integration
**Description:** Verify `--format json` produces valid JSON output.

**Preconditions:**
- Fixture spec directory with known problems.

**Input:**
- CLI invocation: `["lint-spec", "--format", "json"]`

**Expected:**
- Output is valid JSON.
- JSON contains `"findings"` and `"summary"` keys.
- Summary counts match finding severities.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["lint-spec", "--format", "json"])
data = json.loads(result.output)
ASSERT "findings" IN data
ASSERT "summary" IN data
ASSERT data["summary"]["total"] == len(data["findings"])
```

---

### TS-09-E5: YAML output format

**Requirement:** 09-REQ-9.1, 09-REQ-9.3
**Type:** integration
**Description:** Verify `--format yaml` produces valid YAML output.

**Preconditions:**
- Fixture spec directory with known problems.

**Input:**
- CLI invocation: `["lint-spec", "--format", "yaml"]`

**Expected:**
- Output is valid YAML.
- YAML contains `findings` and `summary` keys.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["lint-spec", "--format", "yaml"])
data = yaml.safe_load(result.output)
ASSERT "findings" IN data
ASSERT "summary" IN data
```

---

### TS-09-E6: Table output includes summary line

**Requirement:** 09-REQ-9.2
**Type:** integration
**Description:** Verify table output includes a summary line with counts.

**Preconditions:**
- Fixture spec directory with known problems (at least one error, one warning).

**Input:**
- CLI invocation: `["lint-spec", "--format", "table"]`

**Expected:**
- Output contains severity count text (e.g., "1 error", "1 warning").

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["lint-spec"])
ASSERT "error" IN result.output.lower()
ASSERT "warning" IN result.output.lower()
```

---

### TS-09-E7: Exit code 0 when only warnings

**Requirement:** 09-REQ-9.4, 09-REQ-9.5
**Type:** integration
**Description:** Verify exit code is 0 when only Warning/Hint findings exist.

**Preconditions:**
- Fixture spec directory with complete files (no errors) but oversized groups
  (warnings only).

**Input:**
- CLI invocation: `["lint-spec"]`

**Expected:**
- Exit code 0.
- Output contains warning findings.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["lint-spec"])
ASSERT result.exit_code == 0
```

---

### TS-09-E8: Valid dependencies produce no findings

**Requirement:** 09-REQ-6.1
**Type:** unit
**Description:** Verify `check_broken_dependencies` returns empty for valid
references.

**Preconditions:**
- Fixture spec with a `prd.md` referencing `01_core_foundation` group 1.
- `known_specs` includes `01_core_foundation` with group 1.

**Input:**
- `check_broken_dependencies("test_spec", fixture_path, {"01_core_foundation": [1, 2, 3]})`

**Expected:**
- Returns an empty list.

**Assertion pseudocode:**
```
findings = check_broken_dependencies("test_spec", fixture_path, known_specs)
ASSERT len(findings) == 0
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 09-REQ-1.1 | TS-09-E1, TS-09-E2 | integration |
| 09-REQ-1.2 | TS-09-12 | unit |
| 09-REQ-1.3 | TS-09-12 | unit |
| 09-REQ-1.E1 | TS-09-E1, TS-09-E2 | integration |
| 09-REQ-2.1 | TS-09-1, TS-09-2 | unit |
| 09-REQ-2.2 | TS-09-1 | unit |
| 09-REQ-3.1 | TS-09-3, TS-09-4, TS-09-5 | unit |
| 09-REQ-3.2 | TS-09-3, TS-09-4 | unit |
| 09-REQ-4.1 | TS-09-6, TS-09-7 | unit |
| 09-REQ-4.2 | TS-09-6 | unit |
| 09-REQ-5.1 | TS-09-8 | unit |
| 09-REQ-5.2 | TS-09-8 | unit |
| 09-REQ-6.1 | TS-09-9, TS-09-E8 | unit |
| 09-REQ-6.2 | TS-09-9 | unit |
| 09-REQ-6.3 | TS-09-10 | unit |
| 09-REQ-7.1 | TS-09-11 | unit |
| 09-REQ-7.2 | TS-09-11 | unit |
| 09-REQ-8.1 | (AI tests via mocked client) | unit |
| 09-REQ-8.2 | (AI tests via mocked client) | unit |
| 09-REQ-8.3 | (AI tests via mocked client) | unit |
| 09-REQ-8.E1 | TS-09-E3 | unit |
| 09-REQ-9.1 | TS-09-E4, TS-09-E5, TS-09-E6 | integration |
| 09-REQ-9.2 | TS-09-E6 | integration |
| 09-REQ-9.3 | TS-09-E4, TS-09-E5 | integration |
| 09-REQ-9.4 | TS-09-E1, TS-09-E2 | integration |
| 09-REQ-9.5 | TS-09-E7 | integration |
| Property 1 | TS-09-P5 | property |
| Property 3 | TS-09-P1 | property |
| Property 4 | TS-09-P2 | property |
| Property 5 | TS-09-P3 | property |
| Property 6 | TS-09-P4 | property |
