# Test Specification: Error Auto-Fix

## Overview

Tests for the error auto-fix system: quality check detection, failure
collection, failure clustering, fix spec generation, the iterative fix loop,
report rendering, and the CLI command. Tests map to requirements in
`requirements.md` and correctness properties in `design.md`.

All subprocess invocations are mocked. AI model calls are mocked. No external
processes or API calls are made during testing.

## Test Cases

### TS-08-1: Detect pytest from pyproject.toml

**Requirement:** 08-REQ-1.1, 08-REQ-1.2
**Type:** unit
**Description:** Verify detector finds pytest when pyproject.toml contains
`[tool.pytest.ini_options]`.

**Preconditions:**
- A temporary directory with a `pyproject.toml` containing
  `[tool.pytest.ini_options]\ntestpaths = ["tests"]`.

**Input:**
- `detect_checks(project_root=tmp_dir)`

**Expected:**
- Returns a list containing a CheckDescriptor with name "pytest", command
  `["uv", "run", "pytest"]`, category `CheckCategory.TEST`.

**Assertion pseudocode:**
```
checks = detect_checks(tmp_dir)
pytest_checks = [c for c in checks if c.name == "pytest"]
ASSERT len(pytest_checks) == 1
ASSERT pytest_checks[0].command == ["uv", "run", "pytest"]
ASSERT pytest_checks[0].category == CheckCategory.TEST
```

---

### TS-08-2: Detect ruff and mypy from pyproject.toml

**Requirement:** 08-REQ-1.2, 08-REQ-1.3
**Type:** unit
**Description:** Verify detector finds ruff and mypy when their tool sections
exist in pyproject.toml.

**Preconditions:**
- A temporary directory with a `pyproject.toml` containing `[tool.ruff]` and
  `[tool.mypy]` sections.

**Input:**
- `detect_checks(project_root=tmp_dir)`

**Expected:**
- Returns check descriptors for both ruff (category LINT) and mypy (category
  TYPE).
- Each has the correct command and category.

**Assertion pseudocode:**
```
checks = detect_checks(tmp_dir)
names = {c.name for c in checks}
ASSERT "ruff" IN names
ASSERT "mypy" IN names
ruff = [c for c in checks if c.name == "ruff"][0]
ASSERT ruff.category == CheckCategory.LINT
mypy = [c for c in checks if c.name == "mypy"][0]
ASSERT mypy.category == CheckCategory.TYPE
```

---

### TS-08-3: Detect npm test and lint from package.json

**Requirement:** 08-REQ-1.2
**Type:** unit
**Description:** Verify detector finds npm test and lint scripts from
package.json.

**Preconditions:**
- A temporary directory with a `package.json` containing
  `{"scripts": {"test": "jest", "lint": "eslint ."}}`.

**Input:**
- `detect_checks(project_root=tmp_dir)`

**Expected:**
- Returns check descriptors for "npm test" (category TEST) and "npm lint"
  (category LINT).

**Assertion pseudocode:**
```
checks = detect_checks(tmp_dir)
names = {c.name for c in checks}
ASSERT "npm test" IN names
ASSERT "npm lint" IN names
```

---

### TS-08-4: Detect make test from Makefile

**Requirement:** 08-REQ-1.2
**Type:** unit
**Description:** Verify detector finds make test when Makefile contains a test
target.

**Preconditions:**
- A temporary directory with a `Makefile` containing `test:\n\tpytest`.

**Input:**
- `detect_checks(project_root=tmp_dir)`

**Expected:**
- Returns a check descriptor with name "make test", command `["make", "test"]`,
  category TEST.

**Assertion pseudocode:**
```
checks = detect_checks(tmp_dir)
make_checks = [c for c in checks if c.name == "make test"]
ASSERT len(make_checks) == 1
ASSERT make_checks[0].command == ["make", "test"]
```

---

### TS-08-5: Detect cargo test from Cargo.toml

**Requirement:** 08-REQ-1.2
**Type:** unit
**Description:** Verify detector finds cargo test when Cargo.toml exists with a
`[package]` section.

**Preconditions:**
- A temporary directory with a `Cargo.toml` containing
  `[package]\nname = "myproject"`.

**Input:**
- `detect_checks(project_root=tmp_dir)`

**Expected:**
- Returns a check descriptor with name "cargo test", command
  `["cargo", "test"]`, category TEST.

**Assertion pseudocode:**
```
checks = detect_checks(tmp_dir)
cargo_checks = [c for c in checks if c.name == "cargo test"]
ASSERT len(cargo_checks) == 1
ASSERT cargo_checks[0].category == CheckCategory.TEST
```

---

### TS-08-6: Collector captures failures from failing checks

**Requirement:** 08-REQ-2.1, 08-REQ-2.2
**Type:** unit
**Description:** Verify collector creates FailureRecords for checks that exit
non-zero.

**Preconditions:**
- Mock `subprocess.run` to return exit code 1 with stderr "FAILED test_foo.py".
- A list with one check descriptor (pytest).

**Input:**
- `run_checks(checks=[pytest_descriptor], project_root=tmp_dir)`

**Expected:**
- Returns `([failure], [])` where failure has exit_code 1 and output contains
  "FAILED".

**Assertion pseudocode:**
```
WITH mock subprocess.run RETURNING CompletedProcess(returncode=1, stdout="", stderr="FAILED test_foo.py"):
    failures, passed = run_checks([pytest_check], tmp_dir)
    ASSERT len(failures) == 1
    ASSERT len(passed) == 0
    ASSERT failures[0].exit_code == 1
    ASSERT "FAILED" IN failures[0].output
```

---

### TS-08-7: Collector reports passing checks

**Requirement:** 08-REQ-2.3
**Type:** unit
**Description:** Verify collector correctly reports when all checks pass.

**Preconditions:**
- Mock `subprocess.run` to return exit code 0 for all checks.
- A list with two check descriptors (pytest, ruff).

**Input:**
- `run_checks(checks=[pytest_desc, ruff_desc], project_root=tmp_dir)`

**Expected:**
- Returns `([], [pytest_desc, ruff_desc])` -- no failures, both passed.

**Assertion pseudocode:**
```
WITH mock subprocess.run RETURNING CompletedProcess(returncode=0, stdout="", stderr=""):
    failures, passed = run_checks([pytest_check, ruff_check], tmp_dir)
    ASSERT len(failures) == 0
    ASSERT len(passed) == 2
```

---

### TS-08-8: Fallback clustering groups by check command

**Requirement:** 08-REQ-3.3
**Type:** unit
**Description:** Verify fallback clustering produces one cluster per check
when AI is unavailable.

**Preconditions:**
- Mock Anthropic client to raise an exception (simulating unavailability).
- Two failure records: one from pytest, one from ruff.

**Input:**
- `cluster_failures(failures=[pytest_failure, ruff_failure], config=config)`

**Expected:**
- Returns 2 clusters, one per check command.
- Each cluster contains exactly the failures from that check.

**Assertion pseudocode:**
```
WITH mock AI client RAISING ConnectionError:
    clusters = cluster_failures([pytest_failure, ruff_failure], config)
    ASSERT len(clusters) == 2
    labels = {c.label for c in clusters}
    ASSERT "pytest" IN labels OR any("pytest" in c.label for c in clusters)
```

---

### TS-08-9: AI clustering groups failures semantically

**Requirement:** 08-REQ-3.1, 08-REQ-3.2
**Type:** unit
**Description:** Verify AI clustering parses model response and produces
semantic clusters.

**Preconditions:**
- Mock Anthropic client to return a valid JSON response with two groups.
- Three failure records: two related pytest failures and one ruff failure.

**Input:**
- `cluster_failures(failures=[f1, f2, f3], config=config)`

**Expected:**
- Returns 2 clusters matching the AI response.
- Each cluster has a descriptive label and suggested approach.
- All three failures are accounted for across the clusters.

**Assertion pseudocode:**
```
ai_response = '{"groups": [{"label": "Missing import", "failure_indices": [0, 1], "suggested_approach": "Add import"}, {"label": "Style violation", "failure_indices": [2], "suggested_approach": "Fix formatting"}]}'
WITH mock AI client RETURNING ai_response:
    clusters = cluster_failures([f1, f2, f3], config)
    ASSERT len(clusters) == 2
    total_failures = sum(len(c.failures) for c in clusters)
    ASSERT total_failures == 3
    ASSERT all(c.label != "" for c in clusters)
    ASSERT all(c.suggested_approach != "" for c in clusters)
```

---

### TS-08-10: Fix spec generation creates directory with files

**Requirement:** 08-REQ-4.1, 08-REQ-4.2
**Type:** unit
**Description:** Verify spec generator creates the expected directory and files.

**Preconditions:**
- A temporary output directory.
- A failure cluster with label "Missing return types" and one failure record.

**Input:**
- `generate_fix_spec(cluster=cluster, output_dir=tmp_dir, pass_number=1)`

**Expected:**
- A directory is created under tmp_dir with a sanitized name.
- The directory contains requirements.md, design.md, tasks.md.
- The returned FixSpec has a non-empty task_prompt.

**Assertion pseudocode:**
```
spec = generate_fix_spec(cluster, tmp_dir, pass_number=1)
ASSERT spec.spec_dir.exists()
ASSERT (spec.spec_dir / "requirements.md").exists()
ASSERT (spec.spec_dir / "design.md").exists()
ASSERT (spec.spec_dir / "tasks.md").exists()
ASSERT len(spec.task_prompt) > 0
```

---

### TS-08-11: Fix loop terminates when all checks pass

**Requirement:** 08-REQ-5.1, 08-REQ-5.2
**Type:** unit
**Description:** Verify the fix loop terminates with ALL_FIXED when checks pass
on the first pass.

**Preconditions:**
- Mock `detect_checks` to return one check (pytest).
- Mock `run_checks` to return no failures.
- Mock SessionRunner (should not be called).

**Input:**
- `await run_fix_loop(project_root=tmp_dir, config=config, max_passes=3)`

**Expected:**
- Returns FixResult with termination_reason ALL_FIXED.
- passes_completed == 1.
- sessions_consumed == 0.
- clusters_remaining == 0.

**Assertion pseudocode:**
```
WITH mock run_checks RETURNING ([], [pytest_check]):
    result = await run_fix_loop(tmp_dir, config, max_passes=3)
    ASSERT result.termination_reason == TerminationReason.ALL_FIXED
    ASSERT result.passes_completed == 1
    ASSERT result.sessions_consumed == 0
    ASSERT result.clusters_remaining == 0
```

---

### TS-08-12: Fix loop terminates at max passes

**Requirement:** 08-REQ-5.2
**Type:** unit
**Description:** Verify the fix loop stops after max_passes even if failures
remain.

**Preconditions:**
- Mock `detect_checks` to return one check.
- Mock `run_checks` to always return one failure.
- Mock `cluster_failures` to return one cluster.
- Mock `generate_fix_spec` and SessionRunner.

**Input:**
- `await run_fix_loop(project_root=tmp_dir, config=config, max_passes=2)`

**Expected:**
- Returns FixResult with termination_reason MAX_PASSES.
- passes_completed == 2.
- clusters_remaining > 0.

**Assertion pseudocode:**
```
WITH mock run_checks ALWAYS RETURNING ([failure], []):
    result = await run_fix_loop(tmp_dir, config, max_passes=2)
    ASSERT result.termination_reason == TerminationReason.MAX_PASSES
    ASSERT result.passes_completed == 2
    ASSERT result.clusters_remaining > 0
```

---

### TS-08-13: Fix report renders to console

**Requirement:** 08-REQ-6.1, 08-REQ-6.2
**Type:** unit
**Description:** Verify report rendering produces expected output.

**Preconditions:**
- A FixResult with passes_completed=2, clusters_resolved=3,
  clusters_remaining=1, sessions_consumed=4,
  termination_reason=MAX_PASSES.

**Input:**
- `render_fix_report(result=fix_result, console=console)`

**Expected:**
- Console output contains "2" (passes), "3" (resolved), "1" (remaining),
  "4" (sessions), and "max passes" or "MAX_PASSES".

**Assertion pseudocode:**
```
console = Console(file=StringIO())
render_fix_report(fix_result, console)
output = console.file.getvalue()
ASSERT "2" IN output
ASSERT "3" IN output
ASSERT "1" IN output
ASSERT "4" IN output
ASSERT "max" IN output.lower() OR "MAX_PASSES" IN output
```

## Property Test Cases

### TS-08-P1: Detection determinism

**Property:** Property 1 from design.md
**Validates:** 08-REQ-1.1, 08-REQ-1.2
**Type:** property
**Description:** Detection is deterministic for a fixed project structure.

**For any:** temporary directory with a fixed set of config files
**Invariant:** `detect_checks(root)` called twice returns identical results.

**Assertion pseudocode:**
```
FOR ANY config_files IN valid_config_combinations():
    create_project(tmp_dir, config_files)
    result1 = detect_checks(tmp_dir)
    result2 = detect_checks(tmp_dir)
    ASSERT result1 == result2
```

---

### TS-08-P2: Collector completeness

**Property:** Property 2 from design.md
**Validates:** 08-REQ-2.1, 08-REQ-2.2, 08-REQ-2.3
**Type:** property
**Description:** Every check appears in exactly one of failures or passed.

**For any:** list of check descriptors and mock subprocess results
**Invariant:** `len(failures) + len(passed) == len(checks)` and no check
appears in both.

**Assertion pseudocode:**
```
FOR ANY checks IN lists(check_descriptors), exit_codes IN lists(integers(0, 1)):
    WITH mock subprocess returning exit_codes:
        failures, passed = run_checks(checks, tmp_dir)
        ASSERT len(failures) + len(passed) == len(checks)
        failed_names = {f.check.name for f in failures}
        passed_names = {p.name for p in passed}
        ASSERT failed_names.isdisjoint(passed_names)
```

---

### TS-08-P3: Cluster coverage

**Property:** Property 3 from design.md
**Validates:** 08-REQ-3.1, 08-REQ-3.3
**Type:** property
**Description:** Clustering preserves all failures -- none lost or duplicated.

**For any:** non-empty list of failure records (using fallback clustering)
**Invariant:** The union of all cluster failures equals the input list.

**Assertion pseudocode:**
```
FOR ANY failures IN non_empty_lists(failure_records):
    clusters = _fallback_cluster(failures)
    all_clustered = []
    FOR cluster IN clusters:
        all_clustered.extend(cluster.failures)
    ASSERT set(id(f) for f in all_clustered) == set(id(f) for f in failures)
```

---

### TS-08-P4: Loop termination bound

**Property:** Property 4 from design.md
**Validates:** 08-REQ-5.1, 08-REQ-5.2
**Type:** property
**Description:** The fix loop never exceeds max_passes iterations.

**For any:** max_passes >= 1
**Invariant:** result.passes_completed <= max_passes

**Assertion pseudocode:**
```
FOR ANY max_passes IN integers(min_value=1, max_value=10):
    WITH mock run_checks ALWAYS RETURNING failures:
        result = await run_fix_loop(tmp_dir, config, max_passes=max_passes)
        ASSERT result.passes_completed <= max_passes
```

---

### TS-08-P5: Report field consistency

**Property:** Property 5 from design.md
**Validates:** 08-REQ-6.1, 08-REQ-6.2
**Type:** property
**Description:** FixResult fields are internally consistent.

**For any:** valid FixResult
**Invariant:** passes_completed >= 0, clusters_resolved >= 0,
clusters_remaining >= 0, sessions_consumed >= 0, termination_reason is valid.

**Assertion pseudocode:**
```
FOR ANY result IN valid_fix_results():
    ASSERT result.passes_completed >= 0
    ASSERT result.clusters_resolved >= 0
    ASSERT result.clusters_remaining >= 0
    ASSERT result.sessions_consumed >= 0
    ASSERT result.termination_reason IN TerminationReason
```

## Edge Case Tests

### TS-08-E1: No quality checks detected

**Requirement:** 08-REQ-1.E1
**Type:** unit
**Description:** Verify the system errors when no checks are found.

**Preconditions:**
- A temporary directory with no configuration files (no pyproject.toml, no
  package.json, no Makefile, no Cargo.toml).

**Input:**
- `detect_checks(project_root=empty_tmp_dir)`

**Expected:**
- Returns an empty list.
- When the CLI command calls detect_checks and gets an empty list, it exits
  with non-zero code and an error message.

**Assertion pseudocode:**
```
checks = detect_checks(empty_dir)
ASSERT len(checks) == 0
# CLI layer test:
result = cli_runner.invoke(fix_cmd, [])
ASSERT result.exit_code != 0
ASSERT "no" IN result.output.lower() AND "check" IN result.output.lower()
```

---

### TS-08-E2: Unparseable config file

**Requirement:** 08-REQ-1.E2
**Type:** unit
**Description:** Verify detector skips unparseable config files and continues.

**Preconditions:**
- A temporary directory with an invalid `pyproject.toml` (bad TOML syntax) and
  a valid `package.json` with a test script.

**Input:**
- `detect_checks(project_root=tmp_dir)`

**Expected:**
- Returns checks detected from package.json only.
- Invalid pyproject.toml is skipped (logged, not raised).

**Assertion pseudocode:**
```
checks = detect_checks(tmp_dir)
ASSERT len(checks) >= 1
names = {c.name for c in checks}
ASSERT "npm test" IN names
# pyproject-based checks are absent due to parse error
```

---

### TS-08-E3: Check command timeout

**Requirement:** 08-REQ-2.E1
**Type:** unit
**Description:** Verify collector records timeout as a failure.

**Preconditions:**
- Mock `subprocess.run` to raise `subprocess.TimeoutExpired`.

**Input:**
- `run_checks(checks=[slow_check], project_root=tmp_dir)`

**Expected:**
- Returns one failure record with "timeout" in the output.
- Does not raise an exception.

**Assertion pseudocode:**
```
WITH mock subprocess.run RAISING TimeoutExpired:
    failures, passed = run_checks([slow_check], tmp_dir)
    ASSERT len(failures) == 1
    ASSERT "timeout" IN failures[0].output.lower()
    ASSERT len(passed) == 0
```

---

### TS-08-E4: AI clustering response unparseable

**Requirement:** 08-REQ-3.3
**Type:** unit
**Description:** Verify clusterer falls back when AI returns invalid JSON.

**Preconditions:**
- Mock Anthropic client to return "This is not valid JSON".
- Two failure records from different checks.

**Input:**
- `cluster_failures(failures=[f1, f2], config=config)`

**Expected:**
- Falls back to one cluster per check.
- All failures are preserved in the clusters.

**Assertion pseudocode:**
```
WITH mock AI client RETURNING "not valid json":
    clusters = cluster_failures([f1, f2], config)
    ASSERT len(clusters) == 2  # fallback: one per check
    total = sum(len(c.failures) for c in clusters)
    ASSERT total == 2
```

---

### TS-08-E5: Max passes clamped to 1

**Requirement:** 08-REQ-7.E1
**Type:** unit
**Description:** Verify --max-passes 0 is clamped to 1.

**Preconditions:**
- CLI runner available.

**Input:**
- CLI invocation with `["fix", "--max-passes", "0"]`.

**Expected:**
- The effective max_passes used is 1 (clamped).
- A warning is logged or printed.

**Assertion pseudocode:**
```
# Test via the loop directly:
result = await run_fix_loop(tmp_dir, config, max_passes=0)
# The loop should clamp and run at least 1 pass
ASSERT result.passes_completed >= 0
ASSERT result.passes_completed <= 1
```

---

### TS-08-E6: Fix spec cleanup removes generated directories

**Requirement:** 08-REQ-4.2
**Type:** unit
**Description:** Verify cleanup_fix_specs removes all generated spec
directories.

**Preconditions:**
- A temporary directory with two generated fix spec subdirectories.

**Input:**
- `cleanup_fix_specs(output_dir=tmp_dir)`

**Expected:**
- All subdirectories under output_dir are removed.
- The output_dir itself may or may not exist (implementation choice).

**Assertion pseudocode:**
```
generate_fix_spec(cluster1, tmp_dir, 1)
generate_fix_spec(cluster2, tmp_dir, 1)
ASSERT any(tmp_dir.iterdir())  # specs exist
cleanup_fix_specs(tmp_dir)
ASSERT NOT any(tmp_dir.iterdir())  # all cleaned up
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 08-REQ-1.1 | TS-08-1 | unit |
| 08-REQ-1.2 | TS-08-1, TS-08-2, TS-08-3, TS-08-4, TS-08-5 | unit |
| 08-REQ-1.3 | TS-08-2 | unit |
| 08-REQ-1.E1 | TS-08-E1 | unit |
| 08-REQ-1.E2 | TS-08-E2 | unit |
| 08-REQ-2.1 | TS-08-6 | unit |
| 08-REQ-2.2 | TS-08-6 | unit |
| 08-REQ-2.3 | TS-08-7 | unit |
| 08-REQ-2.E1 | TS-08-E3 | unit |
| 08-REQ-3.1 | TS-08-9 | unit |
| 08-REQ-3.2 | TS-08-9 | unit |
| 08-REQ-3.3 | TS-08-8 | unit |
| 08-REQ-4.1 | TS-08-10 | unit |
| 08-REQ-4.2 | TS-08-10, TS-08-E6 | unit |
| 08-REQ-5.1 | TS-08-11, TS-08-12 | unit |
| 08-REQ-5.2 | TS-08-11, TS-08-12 | unit |
| 08-REQ-5.3 | TS-08-11 | unit |
| 08-REQ-6.1 | TS-08-13 | unit |
| 08-REQ-6.2 | TS-08-13 | unit |
| 08-REQ-7.1 | TS-08-E1 (CLI part) | unit |
| 08-REQ-7.2 | TS-08-E5 | unit |
| 08-REQ-7.E1 | TS-08-E5 | unit |
| Property 1 | TS-08-P1 | property |
| Property 2 | TS-08-P2 | property |
| Property 3 | TS-08-P3 | property |
| Property 4 | TS-08-P4 | property |
| Property 5 | TS-08-P5 | property |
