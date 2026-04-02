# Test Specification: Quality Gate Hunt Category

## Overview

Tests validate the quality_gate hunt category's check detection, execution,
AI analysis, severity mapping, configuration, and error handling. Unit tests
mock subprocess execution and AI responses. Property tests verify invariants
across generated check combinations.

## Test Cases

### TS-67-1: Detect and Execute Checks

**Requirement:** 67-REQ-1.1, 67-REQ-2.1
**Type:** unit
**Description:** Static phase calls `detect_checks()` and executes each
detected check.

**Preconditions:**
- `detect_checks()` is mocked to return two CheckDescriptors (pytest, ruff).
- `subprocess.run()` is mocked to return exit code 1 for both.

**Input:**
- `project_root = Path("/fake/project")`

**Expected:**
- `detect_checks()` called once with `project_root`.
- `subprocess.run()` called twice (once per check).
- Static phase returns a non-empty string containing both check names.

**Assertion pseudocode:**
```
mock detect_checks -> [pytest_check, ruff_check]
mock subprocess.run -> exit code 1, output "error details"
result = await category._run_static_tool(project_root)
ASSERT "pytest" IN result
ASSERT "ruff" IN result
ASSERT detect_checks called_with(project_root)
```

### TS-67-2: Passing Checks Excluded from Output

**Requirement:** 67-REQ-2.3
**Type:** unit
**Description:** Checks that exit 0 are excluded from static phase output.

**Preconditions:**
- `detect_checks()` returns two checks: pytest (fails), ruff (passes).

**Input:**
- pytest exits with code 1, ruff exits with code 0.

**Expected:**
- Static phase output contains "pytest" but not "ruff".

**Assertion pseudocode:**
```
mock detect_checks -> [pytest_check, ruff_check]
mock subprocess.run -> [exit 1 for pytest, exit 0 for ruff]
result = await category._run_static_tool(project_root)
ASSERT "pytest" IN result
ASSERT "ruff" NOT IN result
```

### TS-67-3: One Finding per Failing Check via AI

**Requirement:** 67-REQ-3.1, 67-REQ-3.2
**Type:** unit
**Description:** AI phase produces exactly one Finding per failing check.

**Preconditions:**
- Static phase output describes two failing checks (pytest, mypy).
- AI client mocked to return valid JSON with two finding objects.

**Input:**
- Formatted failure output for pytest and mypy.

**Expected:**
- Exactly 2 Findings returned.
- Each Finding has `category == "quality_gate"`.

**Assertion pseudocode:**
```
mock AI response -> [{"check_name": "pytest", ...}, {"check_name": "mypy", ...}]
findings = await category._run_ai_analysis(project_root, static_output)
ASSERT len(findings) == 2
ASSERT all(f.category == "quality_gate" for f in findings)
```

### TS-67-4: Finding Evidence Contains Raw Output

**Requirement:** 67-REQ-3.3
**Type:** unit
**Description:** Each Finding's evidence field contains the check's raw output.

**Preconditions:**
- One check (pytest) fails with known output text.
- AI analysis returns a finding for pytest.

**Input:**
- pytest output: "FAILED test_foo.py::test_bar - AssertionError"

**Expected:**
- Finding's `evidence` field contains the raw output text.

**Assertion pseudocode:**
```
findings = await category.detect(project_root, config)
ASSERT "FAILED test_foo.py::test_bar" IN findings[0].evidence
```

### TS-67-5: Group Key Format

**Requirement:** 67-REQ-3.4
**Type:** unit
**Description:** Finding group_key uses the format "quality_gate:{check_name}".

**Preconditions:**
- One check (pytest) fails.

**Input:**
- pytest failure output.

**Expected:**
- Finding's `group_key` is `"quality_gate:pytest"`.

**Assertion pseudocode:**
```
findings = await category.detect(project_root, config)
ASSERT findings[0].group_key == "quality_gate:pytest"
```

### TS-67-6: Severity Mapping for Test Category

**Requirement:** 67-REQ-4.1
**Type:** unit
**Description:** Failing test-category checks produce critical-severity findings.

**Preconditions:**
- pytest (category=TEST) fails.

**Input:**
- pytest failure.

**Expected:**
- Finding severity is "critical".

**Assertion pseudocode:**
```
findings = await category.detect(project_root, config)
ASSERT findings[0].severity == "critical"
```

### TS-67-7: Severity Mapping for Type Category

**Requirement:** 67-REQ-4.2
**Type:** unit
**Description:** Failing type-category checks produce major-severity findings.

**Preconditions:**
- mypy (category=TYPE) fails.

**Input:**
- mypy failure.

**Expected:**
- Finding severity is "major".

**Assertion pseudocode:**
```
findings = await category.detect(project_root, config)
ASSERT findings[0].severity == "major"
```

### TS-67-8: Severity Mapping for Lint Category

**Requirement:** 67-REQ-4.3
**Type:** unit
**Description:** Failing lint-category checks produce minor-severity findings.

**Preconditions:**
- ruff (category=LINT) fails.

**Input:**
- ruff failure.

**Expected:**
- Finding severity is "minor".

**Assertion pseudocode:**
```
findings = await category.detect(project_root, config)
ASSERT findings[0].severity == "minor"
```

### TS-67-9: Config Toggle Disables Category

**Requirement:** 67-REQ-5.1
**Type:** unit
**Description:** Setting `quality_gate = false` in config excludes the
category from the registry's enabled list.

**Preconditions:**
- NightShiftCategoryConfig with `quality_gate=False`.

**Input:**
- Config object with quality_gate disabled.

**Expected:**
- `HuntCategoryRegistry.enabled(config)` does not include
  QualityGateCategory.

**Assertion pseudocode:**
```
config.night_shift.categories.quality_gate = False
enabled = registry.enabled(config)
ASSERT not any(c.name == "quality_gate" for c in enabled)
```

### TS-67-10: Default Timeout Value

**Requirement:** 67-REQ-5.2
**Type:** unit
**Description:** Default quality_gate_timeout is 600 seconds.

**Preconditions:**
- Default NightShiftConfig.

**Input:**
- None (default config).

**Expected:**
- `config.quality_gate_timeout == 600`.

**Assertion pseudocode:**
```
config = NightShiftConfig()
ASSERT config.quality_gate_timeout == 600
```

### TS-67-11: Category Registration

**Requirement:** 67-REQ-6.1, 67-REQ-6.2
**Type:** unit
**Description:** QualityGateCategory is registered in the hunt category
registry and exported from the categories package.

**Preconditions:**
- Default HuntCategoryRegistry.

**Input:**
- None.

**Expected:**
- Registry contains a category with name "quality_gate".
- `QualityGateCategory` is importable from
  `agent_fox.nightshift.categories`.

**Assertion pseudocode:**
```
registry = HuntCategoryRegistry()
ASSERT any(c.name == "quality_gate" for c in registry.all())

from agent_fox.nightshift.categories import QualityGateCategory
ASSERT QualityGateCategory is not None
```

## Edge Case Tests

### TS-67-E1: detect_checks Raises Exception

**Requirement:** 67-REQ-1.E1
**Type:** unit
**Description:** Exception from detect_checks is caught, returns zero findings.

**Preconditions:**
- `detect_checks()` mocked to raise `OSError`.

**Input:**
- Any project root.

**Expected:**
- Zero findings returned.
- Warning logged.

**Assertion pseudocode:**
```
mock detect_checks -> raises OSError("disk error")
findings = await category.detect(project_root, config)
ASSERT findings == []
ASSERT warning logged containing "disk error" or "quality_gate"
```

### TS-67-E2: No Checks Detected

**Requirement:** 67-REQ-1.2
**Type:** unit
**Description:** Empty check list produces zero findings.

**Preconditions:**
- `detect_checks()` returns `[]`.

**Input:**
- Project with no recognised config files.

**Expected:**
- Zero findings returned.

**Assertion pseudocode:**
```
mock detect_checks -> []
findings = await category.detect(project_root, config)
ASSERT findings == []
```

### TS-67-E3: Check Subprocess Timeout

**Requirement:** 67-REQ-2.E1
**Type:** unit
**Description:** Timed-out check is recorded as failure with exit code -1.

**Preconditions:**
- `subprocess.run()` raises `TimeoutExpired` for pytest.

**Input:**
- pytest check with timeout.

**Expected:**
- Static output contains timeout message.
- Finding is still produced for the timed-out check.

**Assertion pseudocode:**
```
mock subprocess.run -> raises TimeoutExpired
result = await category._run_static_tool(project_root)
ASSERT "timeout" IN result.lower()
```

### TS-67-E4: All Checks Pass (Silent)

**Requirement:** 67-REQ-2.E2
**Type:** unit
**Description:** All passing checks produce zero findings.

**Preconditions:**
- Two checks detected, both exit with code 0.

**Input:**
- All checks pass.

**Expected:**
- Zero findings returned.

**Assertion pseudocode:**
```
mock detect_checks -> [pytest_check, ruff_check]
mock subprocess.run -> exit 0 for both
findings = await category.detect(project_root, config)
ASSERT findings == []
```

### TS-67-E5: AI Backend Failure Fallback

**Requirement:** 67-REQ-3.E1
**Type:** unit
**Description:** AI failure triggers mechanical Finding generation.

**Preconditions:**
- One check (pytest) fails.
- AI client mocked to raise an exception.

**Input:**
- pytest failure output.

**Expected:**
- One Finding returned (mechanical fallback).
- Finding title contains the check name.
- Finding description contains the raw output.

**Assertion pseudocode:**
```
mock AI client -> raises RuntimeError
findings = await category.detect(project_root, config)
ASSERT len(findings) == 1
ASSERT "pytest" IN findings[0].title.lower()
```

### TS-67-E6: AI Returns Unparseable JSON

**Requirement:** 67-REQ-3.E1
**Type:** unit
**Description:** Unparseable AI response triggers mechanical fallback.

**Preconditions:**
- One check fails.
- AI returns "not valid json at all".

**Input:**
- Failure output + invalid AI response.

**Expected:**
- One Finding returned via mechanical fallback.

**Assertion pseudocode:**
```
mock AI response text -> "not valid json"
findings = await category._run_ai_analysis(project_root, static_output)
ASSERT len(findings) == 1
```

### TS-67-E7: Timeout Config Clamped

**Requirement:** 67-REQ-5.3
**Type:** unit
**Description:** Timeout values below 60 are clamped.

**Preconditions:**
- None.

**Input:**
- `quality_gate_timeout = 10`

**Expected:**
- Config value clamped to 60.

**Assertion pseudocode:**
```
config = NightShiftConfig(quality_gate_timeout=10)
ASSERT config.quality_gate_timeout == 60
```

## Property Test Cases

### TS-67-P1: Silent on Green

**Property:** Property 1 from design.md
**Validates:** 67-REQ-2.E2, 67-REQ-2.3
**Type:** property
**Description:** If all checks pass, zero findings are produced.

**For any:** List of 1-10 CheckDescriptors where all exit with code 0.
**Invariant:** `len(findings) == 0`

**Assertion pseudocode:**
```
FOR ANY checks IN lists(check_descriptors, min_size=1, max_size=10):
    mock all checks -> exit 0
    findings = await category.detect(project_root, config)
    ASSERT len(findings) == 0
```

### TS-67-P2: One Finding per Failure

**Property:** Property 2 from design.md
**Validates:** 67-REQ-3.2
**Type:** property
**Description:** Number of findings equals number of failing checks.

**For any:** List of 1-10 CheckDescriptors with K failing (0 < K <= N).
**Invariant:** `len(findings) == K`

**Assertion pseudocode:**
```
FOR ANY checks, fail_mask IN (check_lists, boolean_masks):
    K = sum(fail_mask)
    assume(K > 0)
    mock checks with fail_mask
    findings = await category.detect(project_root, config)
    ASSERT len(findings) == K
```

### TS-67-P3: Severity Mapping Consistency

**Property:** Property 3 from design.md
**Validates:** 67-REQ-4.1, 67-REQ-4.2, 67-REQ-4.3, 67-REQ-4.4
**Type:** property
**Description:** Severity always matches the check category mapping.

**For any:** Single failing CheckDescriptor with category in {TEST, LINT,
TYPE, BUILD}.
**Invariant:** Finding severity matches the mapping table.

**Assertion pseudocode:**
```
SEVERITY_MAP = {TEST: "critical", BUILD: "critical", TYPE: "major", LINT: "minor"}
FOR ANY cat IN sampled_from(CheckCategory):
    check = CheckDescriptor(name="x", command=["x"], category=cat)
    mock check -> exit 1
    findings = await category.detect(...)
    ASSERT findings[0].severity == SEVERITY_MAP[cat]
```

### TS-67-P4: Graceful Degradation

**Property:** Property 4 from design.md
**Validates:** 67-REQ-3.E1
**Type:** property
**Description:** AI failure never causes zero findings when failures exist.

**For any:** 1-5 failing checks with AI backend raising exception.
**Invariant:** `len(findings) == len(failing_checks)`

**Assertion pseudocode:**
```
FOR ANY checks IN lists(check_descriptors, min_size=1, max_size=5):
    mock all checks -> exit 1
    mock AI -> raises RuntimeError
    findings = await category.detect(...)
    ASSERT len(findings) == len(checks)
```

### TS-67-P5: No Findings Without Checks

**Property:** Property 5 from design.md
**Validates:** 67-REQ-1.2
**Type:** property
**Description:** Empty check list always yields empty findings.

**For any:** (trivial -- no generation needed)
**Invariant:** `len(findings) == 0`

**Assertion pseudocode:**
```
mock detect_checks -> []
findings = await category.detect(project_root, config)
ASSERT len(findings) == 0
```

### TS-67-P6: Timeout Clamping

**Property:** Property 6 from design.md
**Validates:** 67-REQ-5.3
**Type:** property
**Description:** Timeout values are always >= 60 after config validation.

**For any:** Integer timeout value in range [0, 10000].
**Invariant:** `config.quality_gate_timeout >= 60`

**Assertion pseudocode:**
```
FOR ANY timeout IN integers(min_value=0, max_value=10000):
    config = NightShiftConfig(quality_gate_timeout=timeout)
    ASSERT config.quality_gate_timeout >= 60
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 67-REQ-1.1 | TS-67-1 | unit |
| 67-REQ-1.2 | TS-67-E2, TS-67-P5 | unit, property |
| 67-REQ-1.E1 | TS-67-E1 | unit |
| 67-REQ-2.1 | TS-67-1 | unit |
| 67-REQ-2.2 | TS-67-10 | unit |
| 67-REQ-2.3 | TS-67-2, TS-67-P1 | unit, property |
| 67-REQ-2.4 | TS-67-1 | unit |
| 67-REQ-2.E1 | TS-67-E3 | unit |
| 67-REQ-2.E2 | TS-67-E4, TS-67-P1 | unit, property |
| 67-REQ-3.1 | TS-67-3 | unit |
| 67-REQ-3.2 | TS-67-3, TS-67-P2 | unit, property |
| 67-REQ-3.3 | TS-67-4 | unit |
| 67-REQ-3.4 | TS-67-5 | unit |
| 67-REQ-3.E1 | TS-67-E5, TS-67-E6, TS-67-P4 | unit, property |
| 67-REQ-4.1 | TS-67-6, TS-67-P3 | unit, property |
| 67-REQ-4.2 | TS-67-7, TS-67-P3 | unit, property |
| 67-REQ-4.3 | TS-67-8, TS-67-P3 | unit, property |
| 67-REQ-4.4 | TS-67-P3 | property |
| 67-REQ-5.1 | TS-67-9 | unit |
| 67-REQ-5.2 | TS-67-10 | unit |
| 67-REQ-5.3 | TS-67-E7, TS-67-P6 | unit, property |
| 67-REQ-6.1 | TS-67-11 | unit |
| 67-REQ-6.2 | TS-67-11 | unit |
| 67-REQ-6.3 | TS-67-1 | unit |
