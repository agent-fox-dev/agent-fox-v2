# Test Specification: Transient Audit Reports

## Overview

Tests verify that audit reports are written to `.agent-fox/audit/`, overwritten
per spec, deleted on PASS verdict, and cleaned up on spec completion. All tests
use `tmp_path` fixtures to simulate the project root.

## Test Cases

### TS-92-1: Non-PASS report written to new location

**Requirement:** 92-REQ-1.1
**Type:** unit
**Description:** A FAIL verdict writes the report to `.agent-fox/audit/audit_{spec_name}.md`.

**Preconditions:**
- `tmp_path / ".specs" / "05_foo"` exists (simulates spec_dir).
- `tmp_path / ".agent-fox" / "audit"` does not yet exist.

**Input:**
- `spec_dir = tmp_path / ".specs" / "05_foo"`
- `result` with `overall_verdict = "FAIL"`, one entry.

**Expected:**
- File exists at `tmp_path / ".agent-fox" / "audit" / "audit_05_foo.md"`.
- File contains `"# Audit Report: 05_foo"`.
- No file at `tmp_path / ".specs" / "05_foo" / "audit.md"`.

**Assertion pseudocode:**
```
persist_auditor_results(spec_dir, result)
audit_path = tmp_path / ".agent-fox" / "audit" / "audit_05_foo.md"
ASSERT audit_path.exists()
ASSERT "# Audit Report: 05_foo" in audit_path.read_text()
ASSERT NOT (spec_dir / "audit.md").exists()
```

---

### TS-92-2: Audit directory created automatically

**Requirement:** 92-REQ-1.2
**Type:** unit
**Description:** The `.agent-fox/audit/` directory is created if it does not exist.

**Preconditions:**
- `tmp_path / ".agent-fox" / "audit"` does not exist.
- `tmp_path / ".specs" / "05_foo"` exists.

**Input:**
- `spec_dir = tmp_path / ".specs" / "05_foo"`
- `result` with `overall_verdict = "FAIL"`.

**Expected:**
- `tmp_path / ".agent-fox" / "audit"` is a directory.

**Assertion pseudocode:**
```
persist_auditor_results(spec_dir, result)
ASSERT (tmp_path / ".agent-fox" / "audit").is_dir()
```

---

### TS-92-3: No audit.md in spec directory

**Requirement:** 92-REQ-1.3
**Type:** unit
**Description:** After writing a report, no `audit.md` exists in the spec directory.

**Preconditions:**
- `spec_dir` exists.

**Input:**
- `spec_dir = tmp_path / ".specs" / "10_bar"`
- `result` with `overall_verdict = "WEAK"`.

**Expected:**
- No file at `spec_dir / "audit.md"`.

**Assertion pseudocode:**
```
persist_auditor_results(spec_dir, result)
ASSERT NOT (spec_dir / "audit.md").exists()
```

---

### TS-92-4: Overwrite existing report

**Requirement:** 92-REQ-2.1
**Type:** unit
**Description:** A second audit run for the same spec overwrites the previous report.

**Preconditions:**
- First call with `attempt=1` has already written a report.

**Input:**
- Two calls to `persist_auditor_results` with same `spec_dir`, different
  `attempt` values (1, then 2). Both non-PASS.

**Expected:**
- Only one file exists.
- File content contains `"Attempt:** 2"` (from second call), not
  `"Attempt:** 1"`.

**Assertion pseudocode:**
```
persist_auditor_results(spec_dir, result1, attempt=1)
persist_auditor_results(spec_dir, result2, attempt=2)
content = audit_path.read_text()
ASSERT "**Attempt:** 2" in content
ASSERT "**Attempt:** 1" NOT in content
```

---

### TS-92-5: PASS verdict deletes existing report

**Requirement:** 92-REQ-3.1
**Type:** unit
**Description:** A PASS verdict deletes the audit report and does not write a new one.

**Preconditions:**
- A FAIL report already exists for the spec.

**Input:**
- First call: `result` with `overall_verdict = "FAIL"`.
- Second call: `result` with `overall_verdict = "PASS"`.

**Expected:**
- After second call, the audit file does not exist.

**Assertion pseudocode:**
```
persist_auditor_results(spec_dir, fail_result)
ASSERT audit_path.exists()
persist_auditor_results(spec_dir, pass_result)
ASSERT NOT audit_path.exists()
```

---

### TS-92-6: Cleanup deletes reports for completed specs

**Requirement:** 92-REQ-4.1, 92-REQ-4.2
**Type:** unit
**Description:** `cleanup_completed_spec_audits` deletes reports for completed
specs and leaves others untouched.

**Preconditions:**
- Audit files exist for specs `05_foo` and `10_bar`.
- Only `05_foo` is in the completed set.

**Input:**
- `project_root = tmp_path`
- `completed_specs = {"05_foo"}`

**Expected:**
- `audit_05_foo.md` is deleted.
- `audit_10_bar.md` still exists.

**Assertion pseudocode:**
```
cleanup_completed_spec_audits(tmp_path, {"05_foo"})
ASSERT NOT (audit_dir / "audit_05_foo.md").exists()
ASSERT (audit_dir / "audit_10_bar.md").exists()
```

---

### TS-92-7: GraphSync.completed_spec_names

**Requirement:** 92-REQ-4.1
**Type:** unit
**Description:** `completed_spec_names()` returns only specs where all nodes
are completed.

**Preconditions:**
- Node states: `{"05_foo:1": "completed", "05_foo:2": "completed",
  "10_bar:1": "completed", "10_bar:2": "pending"}`.

**Input:**
- Call `graph_sync.completed_spec_names()`.

**Expected:**
- Returns `{"05_foo"}` (not `"10_bar"` since it has a pending node).

**Assertion pseudocode:**
```
gs = GraphSync(node_states, edges={...})
result = gs.completed_spec_names()
ASSERT result == {"05_foo"}
```

## Edge Case Tests

### TS-92-E1: Directory creation failure

**Requirement:** 92-REQ-1.E1
**Type:** unit
**Description:** Filesystem error on directory creation is logged, not raised.

**Preconditions:**
- Mock `Path.mkdir` to raise `OSError`.

**Input:**
- Call `persist_auditor_results` with a FAIL result.

**Expected:**
- No exception raised.
- Error logged.

**Assertion pseudocode:**
```
with patch("pathlib.Path.mkdir", side_effect=OSError("denied")):
    persist_auditor_results(spec_dir, fail_result)  # no exception
ASSERT "error" in caplog.text.lower() or "failed" in caplog.text.lower()
```

---

### TS-92-E2: PASS deletion when no file exists

**Requirement:** 92-REQ-3.E1
**Type:** unit
**Description:** PASS verdict with no existing file is a no-op.

**Preconditions:**
- No audit file exists for the spec.

**Input:**
- Call `persist_auditor_results` with a PASS result.

**Expected:**
- No exception raised.
- No file created.

**Assertion pseudocode:**
```
persist_auditor_results(spec_dir, pass_result)
ASSERT NOT audit_path.exists()
# no exception
```

---

### TS-92-E3: PASS deletion filesystem error

**Requirement:** 92-REQ-3.E2
**Type:** unit
**Description:** Filesystem error during PASS deletion is logged, not raised.

**Preconditions:**
- Audit file exists but `unlink` raises `OSError`.

**Input:**
- Call `persist_auditor_results` with a PASS result.

**Expected:**
- No exception raised.
- Error logged.

**Assertion pseudocode:**
```
audit_path.write_text("old report")
with patch("pathlib.Path.unlink", side_effect=OSError("denied")):
    persist_auditor_results(spec_dir, pass_result)  # no exception
ASSERT "error" in caplog.text.lower() or "failed" in caplog.text.lower()
```

---

### TS-92-E4: Completion cleanup when no files exist

**Requirement:** 92-REQ-4.E1
**Type:** unit
**Description:** Cleanup with no matching files is a no-op.

**Preconditions:**
- No audit files exist.

**Input:**
- `cleanup_completed_spec_audits(tmp_path, {"05_foo"})`.

**Expected:**
- No exception raised.

**Assertion pseudocode:**
```
cleanup_completed_spec_audits(tmp_path, {"05_foo"})
# no exception
```

---

### TS-92-E5: Completion cleanup partial failure

**Requirement:** 92-REQ-4.E2
**Type:** unit
**Description:** If deletion fails for one spec, the function continues to
process remaining specs.

**Preconditions:**
- Audit files exist for specs `05_foo` and `10_bar`.
- `unlink` for `05_foo` raises `OSError`.

**Input:**
- `cleanup_completed_spec_audits(tmp_path, {"05_foo", "10_bar"})`.

**Expected:**
- `audit_10_bar.md` is deleted despite `05_foo` failure.
- Warning logged.

**Assertion pseudocode:**
```
# patch unlink to fail only for 05_foo
cleanup_completed_spec_audits(tmp_path, {"05_foo", "10_bar"})
ASSERT NOT (audit_dir / "audit_10_bar.md").exists()
ASSERT "warning" in caplog.text.lower() or "failed" in caplog.text.lower()
```

## Property Test Cases

### TS-92-P1: Output location for arbitrary spec names

**Property:** Property 1 from design.md
**Validates:** 92-REQ-1.1, 92-REQ-1.3
**Type:** property
**Description:** For any valid spec name and non-PASS verdict, the report is
written only to `.agent-fox/audit/`.

**For any:** `spec_name` drawn from `text(alphabet=ascii_lowercase + digits + "_", min_size=3, max_size=40)`, `verdict` drawn from `sampled_from(["FAIL", "WEAK"])`.
**Invariant:** After `persist_auditor_results`, a file exists at
`.agent-fox/audit/audit_{spec_name}.md` and no file exists at
`.specs/{spec_name}/audit.md`.

**Assertion pseudocode:**
```
FOR ANY spec_name, verdict:
    spec_dir = tmp_path / ".specs" / spec_name
    spec_dir.mkdir(parents=True, exist_ok=True)
    result = AuditResult(overall_verdict=verdict, entries=[], summary="test")
    persist_auditor_results(spec_dir, result)
    ASSERT (tmp_path / ".agent-fox" / "audit" / f"audit_{spec_name}.md").exists()
    ASSERT NOT (spec_dir / "audit.md").exists()
```

---

### TS-92-P2: PASS always deletes

**Property:** Property 2 from design.md
**Validates:** 92-REQ-3.1, 92-REQ-3.E1
**Type:** property
**Description:** For any spec name, after a PASS verdict, no audit file remains.

**For any:** `spec_name` drawn from `text(...)`, `pre_existing` drawn from `booleans()`.
**Invariant:** After calling `persist_auditor_results` with PASS, no audit file
exists for that spec.

**Assertion pseudocode:**
```
FOR ANY spec_name, pre_existing:
    if pre_existing:
        audit_path.write_text("old")
    result = AuditResult(overall_verdict="PASS", entries=[], summary="ok")
    persist_auditor_results(spec_dir, result)
    ASSERT NOT audit_path.exists()
```

---

### TS-92-P3: Cleanup only deletes matching specs

**Property:** Property 3 from design.md
**Validates:** 92-REQ-4.1, 92-REQ-4.2, 92-REQ-4.E1
**Type:** property
**Description:** Cleanup deletes exactly the files for completed specs.

**For any:** `all_specs` drawn from `sets(text(...), min_size=1, max_size=5)`,
`completed` drawn as a subset of `all_specs`.
**Invariant:** After cleanup, files for completed specs are gone, files for
non-completed specs remain.

**Assertion pseudocode:**
```
FOR ANY all_specs, completed:
    for s in all_specs:
        (audit_dir / f"audit_{s}.md").write_text("report")
    cleanup_completed_spec_audits(project_root, completed)
    for s in completed:
        ASSERT NOT (audit_dir / f"audit_{s}.md").exists()
    for s in all_specs - completed:
        ASSERT (audit_dir / f"audit_{s}.md").exists()
```

---

### TS-92-P4: Overwrite produces single file with latest content

**Property:** Property 4 from design.md
**Validates:** 92-REQ-2.1
**Type:** property
**Description:** Multiple writes for the same spec leave exactly one file
reflecting the last call.

**For any:** `n` drawn from `integers(min_value=1, max_value=5)`.
**Invariant:** After `n` calls, file count is 1 and content matches last
attempt number.

**Assertion pseudocode:**
```
FOR ANY n:
    for i in range(1, n + 1):
        persist_auditor_results(spec_dir, fail_result, attempt=i)
    files = list(audit_dir.glob("audit_spec_name*"))
    ASSERT len(files) == 1
    ASSERT f"**Attempt:** {n}" in files[0].read_text()
```

## Integration Smoke Tests

### TS-92-SMOKE-1: Full lifecycle — FAIL then PASS

**Execution Path:** Path 1 then Path 2 from design.md
**Description:** Audit report appears on FAIL, disappears on PASS, never
touches spec directory.

**Setup:** `tmp_path` as project root. Real `persist_auditor_results` (not
mocked).

**Trigger:** Two sequential calls — first with FAIL, then with PASS.

**Expected side effects:**
- After first call: file exists at `.agent-fox/audit/audit_{spec}.md`.
- After second call: file does not exist.
- At no point does `.specs/{spec}/audit.md` exist.

**Must NOT satisfy with:** Mocking `persist_auditor_results` or `Path.write_text`.

**Assertion pseudocode:**
```
spec_dir = tmp_path / ".specs" / "05_foo"
spec_dir.mkdir(parents=True)
audit_path = tmp_path / ".agent-fox" / "audit" / "audit_05_foo.md"
spec_audit_path = spec_dir / "audit.md"

persist_auditor_results(spec_dir, fail_result)
ASSERT audit_path.exists()
ASSERT NOT spec_audit_path.exists()

persist_auditor_results(spec_dir, pass_result)
ASSERT NOT audit_path.exists()
ASSERT NOT spec_audit_path.exists()
```

---

### TS-92-SMOKE-2: Completion cleanup end-to-end

**Execution Path:** Path 3 from design.md
**Description:** `completed_spec_names` feeds into `cleanup_completed_spec_audits`,
deleting the right files.

**Setup:** `tmp_path` with pre-created audit files for two specs. `GraphSync`
with node states where one spec is fully completed, the other is not.

**Trigger:** Call `completed_spec_names()` then `cleanup_completed_spec_audits`.

**Expected side effects:**
- Completed spec's audit file is deleted.
- Non-completed spec's audit file remains.

**Must NOT satisfy with:** Mocking `GraphSync.completed_spec_names` or
`cleanup_completed_spec_audits`.

**Assertion pseudocode:**
```
node_states = {"05_foo:1": "completed", "05_foo:2": "completed",
               "10_bar:1": "completed", "10_bar:2": "pending"}
gs = GraphSync(node_states, edges={"05_foo:1": [], "05_foo:2": ["05_foo:1"],
                                    "10_bar:1": [], "10_bar:2": ["10_bar:1"]})
completed = gs.completed_spec_names()
cleanup_completed_spec_audits(tmp_path, completed)
ASSERT NOT (audit_dir / "audit_05_foo.md").exists()
ASSERT (audit_dir / "audit_10_bar.md").exists()
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 92-REQ-1.1 | TS-92-1 | unit |
| 92-REQ-1.2 | TS-92-2 | unit |
| 92-REQ-1.3 | TS-92-3 | unit |
| 92-REQ-1.E1 | TS-92-E1 | unit |
| 92-REQ-2.1 | TS-92-4 | unit |
| 92-REQ-3.1 | TS-92-5 | unit |
| 92-REQ-3.E1 | TS-92-E2 | unit |
| 92-REQ-3.E2 | TS-92-E3 | unit |
| 92-REQ-4.1 | TS-92-6, TS-92-7 | unit |
| 92-REQ-4.2 | TS-92-6 | unit |
| 92-REQ-4.E1 | TS-92-E4 | unit |
| 92-REQ-4.E2 | TS-92-E5 | unit |
| Property 1 | TS-92-P1 | property |
| Property 2 | TS-92-P2 | property |
| Property 3 | TS-92-P3 | property |
| Property 4 | TS-92-P4 | property |
| Path 1+2 | TS-92-SMOKE-1 | integration |
| Path 3 | TS-92-SMOKE-2 | integration |
