

# Test Specification: Coder Session Scope Guard

## Overview

This test specification translates every acceptance criterion from the requirements document and every correctness property from the design document into concrete, language-agnostic test contracts. Tests are organized into four categories: acceptance criterion tests (TS-87-N), property tests (TS-87-PN), edge case tests (TS-87-EN), and integration smoke tests (TS-87-SMOKE-N). Test cases reference module interfaces and data types defined in `design.md` and use the `scope_guard/` module namespace throughout.

All tests use concrete inputs wherever possible. Property tests define input generation strategies and invariants. Integration smoke tests traverse full execution paths from `design.md` and must not mock the components named in those paths.

---

## Test Cases

### TS-87-1: Stub constraint directive included in test-writing prompt

**Requirement:** 87-REQ-1.1
**Type:** unit
**Description:** Verifies that building a prompt for a test-writing task group includes the stub-only constraint directive.

**Preconditions:**
- A `TaskGroup` with `archetype="test-writing"`, `spec_number=4`, `number=1`, and at least one deliverable.

**Input:**
- `task_group = TaskGroup(number=1, spec_number=4, archetype="test-writing", deliverables=[Deliverable("src/foo.rs", "foo::validate", 1)], depends_on=[])`
- `scope_result = None`

**Expected:**
- The returned prompt string contains the substring `SCOPE_GUARD:STUB_ONLY`.
- The returned prompt string contains text instructing stub-only output for non-test code.

**Assertion pseudocode:**
```
prompt = prompt_builder.build_prompt(task_group, scope_result=None)
ASSERT "SCOPE_GUARD:STUB_ONLY" IN prompt
ASSERT "stub" IN prompt.lower()
```

---

### TS-87-2: Post-session stub validation detects non-stub implementations

**Requirement:** 87-REQ-1.2
**Type:** unit
**Description:** Verifies that `validate_stubs` scans non-test source files and returns violations for functions with non-stub bodies.

**Preconditions:**
- A `FileChange` for a Rust file containing a function with a full implementation body.
- The task group has `archetype="test-writing"`.

**Input:**
- `file_change = FileChange(file_path="src/validator.rs", language=Language.RUST, diff_text="fn validate() -> bool {\n    let x = compute();\n    x > 0\n}")`
- `task_group = TaskGroup(number=1, spec_number=4, archetype="test-writing", deliverables=[Deliverable("src/validator.rs", "validate", 1)], depends_on=[])`

**Expected:**
- `StubValidationResult.passed == False`
- `StubValidationResult.violations` contains one `ViolationRecord` with `function_id="validate"` and `file_path="src/validator.rs"`.

**Assertion pseudocode:**
```
result = stub_validator.validate_stubs([file_change], task_group)
ASSERT result.passed == False
ASSERT len(result.violations) == 1
ASSERT result.violations[0].function_id == "validate"
ASSERT result.violations[0].file_path == "src/validator.rs"
```

---

### TS-87-3: Stub violation flagged in completion record

**Requirement:** 87-REQ-1.3
**Type:** unit
**Description:** Verifies that when stub violations are found, the resulting `SessionOutcome` has `stub_violation=True` and includes violation details.

**Preconditions:**
- A `StubValidationResult` with `passed=False` and one violation.
- A `SessionResult` with commits from a test-writing task group.

**Input:**
- `session = SessionResult(session_id="sess-001", spec_number=4, task_group_number=1, branch_name="feature/04/1", base_branch="develop", exit_status="success", duration_seconds=120.0, cost_dollars=3.50, modified_files=[FileChange("src/foo.rs", Language.RUST, "fn bar() { compute() }")], commit_count=2)`
- `task_group = TaskGroup(number=1, spec_number=4, archetype="test-writing", deliverables=[Deliverable("src/foo.rs", "bar", 1)], depends_on=[])`

**Expected:**
- `SessionOutcome.stub_violation == True`
- `SessionOutcome.violation_details` is non-empty.
- `SessionOutcome.classification == SessionClassification.SUCCESS` (session succeeded, but violation is flagged).

**Assertion pseudocode:**
```
outcome = session_classifier.classify_session(session, task_group)
ASSERT outcome.stub_violation == True
ASSERT len(outcome.violation_details) >= 1
ASSERT outcome.classification == SessionClassification.SUCCESS
```

---

### TS-87-4: Stub detection for Rust, Python, TypeScript/JavaScript

**Requirement:** 87-REQ-1.4
**Type:** unit
**Description:** Verifies that `is_stub_body` correctly identifies stub placeholders for each supported language.

**Preconditions:**
- None.

**Input:**
- Rust stubs: `"todo!()"`, `"unimplemented!()"`, `'panic!("not implemented")'`
- Python stubs: `"raise NotImplementedError"`, `"pass"`
- TypeScript stubs: `'throw new Error("not implemented")'`
- Non-stubs for each language: `"return 42"`, `"x = 1\nreturn x"`, `"console.log('hi')"`

**Expected:**
- All stub bodies return `True`.
- All non-stub bodies return `False`.

**Assertion pseudocode:**
```
ASSERT is_stub_body("todo!()", Language.RUST) == True
ASSERT is_stub_body("unimplemented!()", Language.RUST) == True
ASSERT is_stub_body('panic!("not implemented")', Language.RUST) == True
ASSERT is_stub_body("return 42", Language.RUST) == False

ASSERT is_stub_body("raise NotImplementedError", Language.PYTHON) == True
ASSERT is_stub_body("pass", Language.PYTHON) == True
ASSERT is_stub_body("x = 1\nreturn x", Language.PYTHON) == False

ASSERT is_stub_body('throw new Error("not implemented")', Language.TYPESCRIPT) == True
ASSERT is_stub_body("console.log('hi')", Language.TYPESCRIPT) == False
```

---

### TS-87-5: Pre-flight scope check returns per-deliverable status

**Requirement:** 87-REQ-2.1
**Type:** unit
**Description:** Verifies that `check_scope` returns a `ScopeCheckResult` with per-deliverable status reflecting the codebase state.

**Preconditions:**
- A codebase directory containing:
  - `src/foo.rs` with function `validate()` having body `todo!()`
  - `src/bar.rs` with function `process()` having body `let result = compute(); result`

**Input:**
- `task_group = TaskGroup(number=2, spec_number=4, archetype="implementation", deliverables=[Deliverable("src/foo.rs", "validate", 2), Deliverable("src/bar.rs", "process", 2)], depends_on=[1])`
- `codebase_root = Path("/tmp/test_codebase")`

**Expected:**
- `ScopeCheckResult.deliverable_results` has 2 entries.
- `validate` → `DeliverableStatus.PENDING`
- `process` → `DeliverableStatus.ALREADY_IMPLEMENTED`
- `ScopeCheckResult.overall == "partially-implemented"`

**Assertion pseudocode:**
```
result = preflight_checker.check_scope(task_group, codebase_root)
ASSERT len(result.deliverable_results) == 2
statuses = {dr.deliverable.function_id: dr.status for dr in result.deliverable_results}
ASSERT statuses["validate"] == DeliverableStatus.PENDING
ASSERT statuses["process"] == DeliverableStatus.ALREADY_IMPLEMENTED
ASSERT result.overall == "partially-implemented"
```

---

### TS-87-6: Pre-flight skip when all deliverables are implemented

**Requirement:** 87-REQ-2.2
**Type:** unit
**Description:** Verifies that `check_scope` returns `overall == "all-implemented"` when all deliverables have non-stub bodies.

**Preconditions:**
- A codebase where every function referenced by the task group has a substantive implementation.

**Input:**
- `task_group` with two deliverables, both pointing to fully implemented functions.
- `codebase_root` pointing to the test codebase.

**Expected:**
- `ScopeCheckResult.overall == "all-implemented"`
- All `deliverable_results` have `status == DeliverableStatus.ALREADY_IMPLEMENTED`

**Assertion pseudocode:**
```
result = preflight_checker.check_scope(task_group, codebase_root)
ASSERT result.overall == "all-implemented"
for dr in result.deliverable_results:
    ASSERT dr.status == DeliverableStatus.ALREADY_IMPLEMENTED
```

---

### TS-87-7: Reduced scope prompt includes only pending deliverables

**Requirement:** 87-REQ-2.3
**Type:** unit
**Description:** Verifies that `build_prompt` with a partially-implemented scope result lists only pending deliverables in the work instructions.

**Preconditions:**
- A `ScopeCheckResult` with two deliverables: one `PENDING` (`"validate"`), one `ALREADY_IMPLEMENTED` (`"process"`).

**Input:**
- `task_group = TaskGroup(number=2, spec_number=4, archetype="implementation", deliverables=[Deliverable("src/foo.rs", "validate", 2), Deliverable("src/bar.rs", "process", 2)], depends_on=[1])`
- `scope_result = ScopeCheckResult(task_group_number=2, deliverable_results=[DeliverableCheckResult(Deliverable("src/foo.rs", "validate", 2), DeliverableStatus.PENDING, "stub body"), DeliverableCheckResult(Deliverable("src/bar.rs", "process", 2), DeliverableStatus.ALREADY_IMPLEMENTED, "has implementation")], overall="partially-implemented", check_duration_ms=50, deliverable_count=2)`

**Expected:**
- Prompt text contains `"validate"` as a work item.
- Prompt text references `"process"` as context/already-implemented, not as work to do.

**Assertion pseudocode:**
```
prompt = prompt_builder.build_prompt(task_group, scope_result)
ASSERT "validate" IN prompt
ASSERT "process" IN prompt
# Verify structural separation (pending in work section, implemented in context section)
work_section = extract_work_section(prompt)
context_section = extract_context_section(prompt)
ASSERT "validate" IN work_section
ASSERT "validate" NOT IN context_section
ASSERT "process" IN context_section
```

---

### TS-87-8: Deliverable status uses stub detection logic

**Requirement:** 87-REQ-2.4
**Type:** unit
**Description:** Verifies that the pre-flight checker classifies deliverables as pending when they contain stubs and already-implemented when they contain non-stubs.

**Preconditions:**
- A file `src/mod.py` containing:
  - `def connect(): raise NotImplementedError` (stub)
  - `def disconnect(): socket.close()` (implemented)

**Input:**
- `task_group` with deliverables for both `connect` and `disconnect`.

**Expected:**
- `connect` classified as `PENDING`.
- `disconnect` classified as `ALREADY_IMPLEMENTED`.

**Assertion pseudocode:**
```
result = preflight_checker.check_scope(task_group, codebase_root)
statuses = {dr.deliverable.function_id: dr.status for dr in result.deliverable_results}
ASSERT statuses["connect"] == DeliverableStatus.PENDING
ASSERT statuses["disconnect"] == DeliverableStatus.ALREADY_IMPLEMENTED
```

---

### TS-87-9: Scope check telemetry logging

**Requirement:** 87-REQ-2.5
**Type:** integration
**Description:** Verifies that the scope check result (duration, deliverable count, per-deliverable status) is persisted to the telemetry store.

**Preconditions:**
- DuckDB telemetry store initialized with the `scope_check_results` table.
- A codebase with at least one deliverable file.

**Input:**
- Perform a scope check for a task group with 2 deliverables.

**Expected:**
- A row is inserted into `scope_check_results` with correct `spec_number`, `task_group_number`, `deliverable_count=2`, non-zero `check_duration_ms`, and a `deliverable_results` JSON array of length 2.

**Assertion pseudocode:**
```
result = preflight_checker.check_scope(task_group, codebase_root)
telemetry.record_scope_check(result)
rows = duckdb.execute("SELECT * FROM scope_check_results WHERE task_group_number = 2")
ASSERT len(rows) == 1
ASSERT rows[0].deliverable_count == 2
ASSERT rows[0].check_duration_ms > 0
ASSERT len(json.loads(rows[0].deliverable_results)) == 2
```

---

### TS-87-10: Overlap detection identifies shared deliverables

**Requirement:** 87-REQ-3.1
**Type:** unit
**Description:** Verifies that `detect_overlaps` identifies deliverables present in multiple task groups.

**Preconditions:**
- A `SpecGraph` with three task groups where TG1 and TG3 both list `Deliverable("src/validator.rs", "validate", _)`.

**Input:**
- `spec_graph = SpecGraph(spec_number=4, task_groups=[TaskGroup(1, 4, "test-writing", [Deliverable("src/validator.rs", "validate", 1)], []), TaskGroup(2, 4, "implementation", [Deliverable("src/engine.rs", "run", 2)], [1]), TaskGroup(3, 4, "implementation", [Deliverable("src/validator.rs", "validate", 3)], [1])])`

**Expected:**
- `OverlapResult.overlaps` contains one `OverlapRecord` with `deliverable_id` referencing `"validate"` in `"src/validator.rs"` and `task_group_numbers == [1, 3]`.

**Assertion pseudocode:**
```
result = overlap_detector.detect_overlaps(spec_graph)
ASSERT len(result.overlaps) == 1
ASSERT set(result.overlaps[0].task_group_numbers) == {1, 3}
ASSERT "validate" IN result.overlaps[0].deliverable_id
```

---

### TS-87-11: Overlap detection emits warning for overlapping task groups

**Requirement:** 87-REQ-3.2
**Type:** unit
**Description:** Verifies that detected overlaps produce warnings listing the overlapping deliverable and conflicting task group numbers.

**Preconditions:**
- A `SpecGraph` with overlapping deliverables between TG1 (depends on nothing) and TG3 (depends on TG1).

**Input:**
- Same spec graph as TS-87-10.

**Expected:**
- `OverlapResult.has_warnings == True`
- The overlap record includes severity information and the involved task groups.

**Assertion pseudocode:**
```
result = overlap_detector.detect_overlaps(spec_graph)
ASSERT result.has_warnings == True
ASSERT len(result.overlaps) >= 1
for overlap in result.overlaps:
    ASSERT len(overlap.task_group_numbers) >= 2
```

---

### TS-87-12: Overlap blocks execution when no dependency relationship

**Requirement:** 87-REQ-3.3
**Type:** unit
**Description:** Verifies that overlap between task groups without a dependency relationship is classified as an error.

**Preconditions:**
- A `SpecGraph` where TG2 and TG3 overlap on a deliverable but neither depends on the other.

**Input:**
- `spec_graph = SpecGraph(spec_number=5, task_groups=[TaskGroup(1, 5, "test-writing", [Deliverable("src/a.rs", "init", 1)], []), TaskGroup(2, 5, "implementation", [Deliverable("src/shared.rs", "process", 2)], [1]), TaskGroup(3, 5, "implementation", [Deliverable("src/shared.rs", "process", 3)], [1])])`

**Expected:**
- `OverlapResult.has_errors == True`
- The overlap record for `"process"` has `severity == OverlapSeverity.ERROR`.

**Assertion pseudocode:**
```
result = overlap_detector.detect_overlaps(spec_graph)
ASSERT result.has_errors == True
error_overlaps = [o for o in result.overlaps if o.severity == OverlapSeverity.ERROR]
ASSERT len(error_overlaps) == 1
ASSERT set(error_overlaps[0].task_group_numbers) == {2, 3}
```

---

### TS-87-13: Overlap warning when dependency relationship exists

**Requirement:** 87-REQ-3.4
**Type:** unit
**Description:** Verifies that overlap between task groups with a dependency relationship is classified as a warning (not error).

**Preconditions:**
- A `SpecGraph` where TG1 and TG3 overlap, and TG3 depends on TG1.

**Input:**
- `spec_graph = SpecGraph(spec_number=4, task_groups=[TaskGroup(1, 4, "test-writing", [Deliverable("src/validator.rs", "validate", 1)], []), TaskGroup(3, 4, "implementation", [Deliverable("src/validator.rs", "validate", 3)], [1])])`

**Expected:**
- `OverlapResult.has_errors == False`
- `OverlapResult.has_warnings == True`
- The overlap record has `severity == OverlapSeverity.WARNING`.

**Assertion pseudocode:**
```
result = overlap_detector.detect_overlaps(spec_graph)
ASSERT result.has_errors == False
ASSERT result.has_warnings == True
ASSERT result.overlaps[0].severity == OverlapSeverity.WARNING
```

---

### TS-87-14: No-op session recorded when zero new commits

**Requirement:** 87-REQ-4.1
**Type:** unit
**Description:** Verifies that a session with zero commits and normal exit is classified as no-op.

**Preconditions:**
- A `SessionResult` with `commit_count=0`, `exit_status="success"`, no modified files.

**Input:**
- `session = SessionResult(session_id="sess-noop-1", spec_number=4, task_group_number=3, branch_name="feature/04/3", base_branch="develop", exit_status="success", duration_seconds=106.0, cost_dollars=3.50, modified_files=[], commit_count=0)`
- `task_group = TaskGroup(number=3, spec_number=4, archetype="implementation", deliverables=[], depends_on=[1])`

**Expected:**
- `SessionOutcome.classification == SessionClassification.NO_OP`

**Assertion pseudocode:**
```
outcome = session_classifier.classify_session(session, task_group)
ASSERT outcome.classification == SessionClassification.NO_OP
```

---

### TS-87-15: Pre-flight skip recorded distinctly from no-op

**Requirement:** 87-REQ-4.2
**Type:** unit
**Description:** Verifies that a pre-flight-skip outcome is stored with classification "pre-flight-skip", distinct from "no-op".

**Preconditions:**
- DuckDB telemetry store initialized.

**Input:**
- `outcome = SessionOutcome(session_id="sess-skip-1", spec_number=4, task_group_number=5, classification=SessionClassification.PRE_FLIGHT_SKIP, duration_seconds=0.0, cost_dollars=0.0, timestamp=datetime(2024, 1, 15, 10, 0, 0), reason="all deliverables already implemented")`

**Expected:**
- After recording, querying `session_outcomes` for `session_id="sess-skip-1"` returns a row with `classification="pre-flight-skip"`.

**Assertion pseudocode:**
```
telemetry.record_session_outcome(outcome)
rows = duckdb.execute("SELECT classification FROM session_outcomes WHERE session_id = 'sess-skip-1'")
ASSERT rows[0].classification == "pre-flight-skip"
```

---

### TS-87-16: No-op/pre-flight-skip telemetry fields completeness

**Requirement:** 87-REQ-4.3
**Type:** unit
**Description:** Verifies that no-op and pre-flight-skip records contain all required fields.

**Preconditions:**
- DuckDB telemetry store initialized.

**Input:**
- `outcome = SessionOutcome(session_id="sess-noop-fields", spec_number=7, task_group_number=2, classification=SessionClassification.NO_OP, duration_seconds=89.5, cost_dollars=3.00, timestamp=datetime(2024, 1, 15, 12, 0, 0), reason="no-op")`

**Expected:**
- Stored row has non-null values for: `spec_number`, `task_group_number`, `duration_seconds`, `cost_dollars`, `timestamp`, `classification`.

**Assertion pseudocode:**
```
telemetry.record_session_outcome(outcome)
row = duckdb.execute("SELECT * FROM session_outcomes WHERE session_id = 'sess-noop-fields'")[0]
ASSERT row.spec_number == 7
ASSERT row.task_group_number == 2
ASSERT row.duration_seconds == 89.5
ASSERT row.cost_dollars == 3.00
ASSERT row.timestamp IS NOT NULL
ASSERT row.classification == "no-op"
```

---

### TS-87-17: Aggregate waste report query

**Requirement:** 87-REQ-4.4
**Type:** integration
**Description:** Verifies that `query_waste_report` returns correct per-specification aggregates of no-op and pre-flight-skip counts, costs, and durations.

**Preconditions:**
- DuckDB telemetry store seeded with:
  - Spec 4: 2 no-ops (cost $3.50 each, 100s each), 1 pre-flight-skip (cost $0, 0s)
  - Spec 7: 1 no-op (cost $4.00, 200s)

**Input:**
- `query_waste_report(spec_number=None)` (all specs)

**Expected:**
- `WasteReport.per_spec` has 2 entries.
- Spec 4: `no_op_count=2`, `pre_flight_skip_count=1`, `total_wasted_cost=7.00`, `total_wasted_duration=200.0`
- Spec 7: `no_op_count=1`, `pre_flight_skip_count=0`, `total_wasted_cost=4.00`, `total_wasted_duration=200.0`

**Assertion pseudocode:**
```
report = telemetry.query_waste_report(spec_number=None)
ASSERT len(report.per_spec) == 2
spec4 = find_by_spec(report.per_spec, 4)
ASSERT spec4.no_op_count == 2
ASSERT spec4.pre_flight_skip_count == 1
ASSERT spec4.total_wasted_cost == 7.00
ASSERT spec4.total_wasted_duration == 200.0
spec7 = find_by_spec(report.per_spec, 7)
ASSERT spec7.no_op_count == 1
ASSERT spec7.pre_flight_skip_count == 0
ASSERT spec7.total_wasted_cost == 4.00
ASSERT spec7.total_wasted_duration == 200.0
```

---

### TS-87-18: Stub directive is machine-parseable in prompt

**Requirement:** 87-REQ-5.1
**Type:** unit
**Description:** Verifies that the prompt for a test-writing session contains the `SCOPE_GUARD:STUB_ONLY` tagged block and is machine-parseable.

**Preconditions:**
- A test-writing `TaskGroup`.

**Input:**
- `task_group = TaskGroup(number=1, spec_number=10, archetype="test-writing", deliverables=[Deliverable("src/x.py", "init", 1)], depends_on=[])`

**Expected:**
- Prompt contains `<!-- SCOPE_GUARD:STUB_ONLY -->` opening tag.
- Prompt contains `<!-- /SCOPE_GUARD:STUB_ONLY -->` closing tag.
- The directive block appears between the tags.

**Assertion pseudocode:**
```
prompt = prompt_builder.build_prompt(task_group)
ASSERT "<!-- SCOPE_GUARD:STUB_ONLY -->" IN prompt
ASSERT "<!-- /SCOPE_GUARD:STUB_ONLY -->" IN prompt
open_idx = prompt.index("<!-- SCOPE_GUARD:STUB_ONLY -->")
close_idx = prompt.index("<!-- /SCOPE_GUARD:STUB_ONLY -->")
ASSERT open_idx < close_idx
```

---

### TS-87-19: Prompt text persisted in telemetry store

**Requirement:** 87-REQ-5.2
**Type:** integration
**Description:** Verifies that the full prompt text is stored and retrievable from the telemetry store.

**Preconditions:**
- DuckDB telemetry store initialized.

**Input:**
- `persist_prompt("sess-prompt-1", "This is a test prompt with SCOPE_GUARD:STUB_ONLY directive")`

**Expected:**
- `get_session_prompt("sess-prompt-1")` returns a `PromptRecord` with the stored prompt text.

**Assertion pseudocode:**
```
telemetry.persist_prompt("sess-prompt-1", "This is a test prompt with SCOPE_GUARD:STUB_ONLY directive")
record = telemetry.get_session_prompt("sess-prompt-1")
ASSERT record IS NOT NULL
ASSERT record.session_id == "sess-prompt-1"
ASSERT "SCOPE_GUARD:STUB_ONLY" IN record.prompt_text
ASSERT record.stub_directive_present == True
ASSERT record.truncated == False
```

---

### TS-87-20: Stub violation record includes prompt directive presence

**Requirement:** 87-REQ-5.3
**Type:** unit
**Description:** Verifies that when a stub violation is recorded, it includes whether the stub constraint directive was present in the session's prompt.

**Preconditions:**
- A persisted prompt for session "sess-viol-1" that contains the `SCOPE_GUARD:STUB_ONLY` directive.
- A stub validation result with violations.

**Input:**
- Prompt persisted with directive present.
- `ViolationRecord` for the session.

**Expected:**
- `ViolationRecord.prompt_directive_present == True`

**Assertion pseudocode:**
```
telemetry.persist_prompt("sess-viol-1", "prompt with <!-- SCOPE_GUARD:STUB_ONLY --> ... <!-- /SCOPE_GUARD:STUB_ONLY -->")
# After validation produces violation, check prompt:
prompt_record = telemetry.get_session_prompt("sess-viol-1")
ASSERT prompt_record.stub_directive_present == True
# The violation record should indicate directive was present (agent ignored it)
violation = ViolationRecord("src/foo.rs", "bar", "let x = 1; x", prompt_directive_present=prompt_record.stub_directive_present)
ASSERT violation.prompt_directive_present == True
```

---

## Property Test Cases

### TS-87-P1: Stub Body Purity

**Property:** Property 1 from design.md
**Validates:** 87-REQ-1.2, 87-REQ-1.4, 87-REQ-1.E2
**Type:** property
**Description:** For any function body in a supported language, `is_stub_body` returns True iff the body (after stripping comments/whitespace) is exactly one recognized stub placeholder.

**For any:** `body` drawn from: (a) all single recognized stub patterns per language, (b) stub patterns with leading/trailing whitespace and comments, (c) stub patterns with additional statements prepended or appended, (d) random non-stub code strings, (e) empty strings.
**Invariant:** `is_stub_body(body, language) == True` iff stripping comments and whitespace yields exactly one recognized stub placeholder and nothing else.

**Assertion pseudocode:**
```
FOR ANY (body, language) IN generated_pairs:
    stripped = strip_comments_and_whitespace(body, language)
    expected = matches_single_stub_pattern(stripped, language)
    ASSERT is_stub_body(body, language) == expected
```

---

### TS-87-P2: Test Block Exclusion

**Property:** Property 2 from design.md
**Validates:** 87-REQ-1.E1
**Type:** property
**Description:** `validate_stubs` excludes functions inside test blocks from stub enforcement and includes functions outside test blocks.

**For any:** A file containing N functions, some inside test blocks and some outside, with a mix of stub and non-stub bodies.
**Invariant:** Functions inside test blocks never appear in `violations`. Functions outside test blocks with non-stub bodies always appear in `violations`.

**Assertion pseudocode:**
```
FOR ANY file_with_mixed_functions IN generated_files:
    result = stub_validator.validate_stubs([file_with_mixed_functions], test_writing_tg)
    for violation in result.violations:
        func = lookup_function(file_with_mixed_functions, violation.function_id)
        ASSERT func.inside_test_block == False
    for func in all_non_test_non_stub_functions(file_with_mixed_functions):
        ASSERT func.function_id IN [v.function_id for v in result.violations]
```

---

### TS-87-P3: Stub Validation Completeness

**Property:** Property 3 from design.md
**Validates:** 87-REQ-1.2, 87-REQ-1.3
**Type:** property
**Description:** For any set of modified files from a test-writing session, every non-stub function outside test blocks appears in violations, and every stub function is absent from violations.

**For any:** A list of `FileChange` objects with known stub/non-stub function bodies and known test-block boundaries.
**Invariant:** `violations` == set of all non-test, non-stub functions in modified files. No stub function appears in violations.

**Assertion pseudocode:**
```
FOR ANY modified_files IN generated_file_lists:
    result = stub_validator.validate_stubs(modified_files, test_writing_tg)
    violation_ids = {v.function_id for v in result.violations}
    for func in all_functions(modified_files):
        if func