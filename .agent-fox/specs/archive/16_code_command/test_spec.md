# Test Specification: Code Command

## Overview

Tests validate the `agent-fox code` CLI command wrapper. All tests use Click's
`CliRunner` with the orchestrator mocked — no real sessions are dispatched.
Tests cover command registration, CLI option overrides, summary output, exit
code mapping, and error handling.

## Test Cases

### TS-16-1: Command Is Registered

**Requirement:** 16-REQ-1.1
**Type:** unit
**Description:** The `code` command is accessible via the main CLI group.

**Preconditions:**
- The Click app is importable.

**Input:**
- Invoke `main` with `["code", "--help"]`.

**Expected:**
- Exit code 0.
- Output contains "Execute the task plan" (the command's help text).

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["code", "--help"])
ASSERT result.exit_code == 0
ASSERT "Execute the task plan" IN result.output
```

---

### TS-16-2: Successful Execution Prints Summary

**Requirement:** 16-REQ-3.1, 16-REQ-3.2, 16-REQ-4.1
**Type:** unit
**Description:** A completed run prints a compact summary and exits 0.

**Preconditions:**
- Orchestrator mocked to return `ExecutionState` with run_status="completed",
  3 completed tasks, 100k input tokens, 50k output tokens, $2.50 cost.
- Plan file exists.
- Config available in Click context.

**Input:**
- Invoke `main` with `["code"]`.

**Expected:**
- Exit code 0.
- Output contains "Tasks:" with "3/3 done".
- Output contains "Tokens:" with token counts.
- Output contains "$2.50".
- Output contains "completed".

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["code"])
ASSERT result.exit_code == 0
ASSERT "3/3 done" IN result.output
ASSERT "$2.50" IN result.output
```

---

### TS-16-3: Parallel Override Applied

**Requirement:** 16-REQ-2.1, 16-REQ-2.5
**Type:** unit
**Description:** The `--parallel` option overrides the config value.

**Preconditions:**
- Orchestrator mocked; captures the config it receives.
- Default config has `parallel=1`.

**Input:**
- Invoke `main` with `["code", "--parallel", "4"]`.

**Expected:**
- The `OrchestratorConfig` passed to `Orchestrator.__init__` has `parallel=4`.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["code", "--parallel", "4"])
ASSERT captured_config.parallel == 4
```

---

### TS-16-4: Max-Cost Override Applied

**Requirement:** 16-REQ-2.3, 16-REQ-2.5
**Type:** unit
**Description:** The `--max-cost` option overrides the config value.

**Preconditions:**
- Orchestrator mocked; captures the config it receives.
- Default config has `max_cost=None`.

**Input:**
- Invoke `main` with `["code", "--max-cost", "10.00"]`.

**Expected:**
- The `OrchestratorConfig` passed to `Orchestrator.__init__` has `max_cost=10.0`.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["code", "--max-cost", "10.00"])
ASSERT captured_config.max_cost == 10.0
```

---

### TS-16-5: Max-Sessions Override Applied

**Requirement:** 16-REQ-2.4, 16-REQ-2.5
**Type:** unit
**Description:** The `--max-sessions` option overrides the config value.

**Preconditions:**
- Orchestrator mocked; captures the config it receives.

**Input:**
- Invoke `main` with `["code", "--max-sessions", "20"]`.

**Expected:**
- The `OrchestratorConfig` passed to `Orchestrator.__init__` has `max_sessions=20`.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["code", "--max-sessions", "20"])
ASSERT captured_config.max_sessions == 20
```

---

### TS-16-6: Stalled Execution Exits With Code 2

**Requirement:** 16-REQ-4.3
**Type:** unit
**Description:** A stalled run exits with code 2.

**Preconditions:**
- Orchestrator mocked to return `ExecutionState` with run_status="stalled".

**Input:**
- Invoke `main` with `["code"]`.

**Expected:**
- Exit code 2.
- Output contains "stalled".

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["code"])
ASSERT result.exit_code == 2
```

---

### TS-16-7: Cost Limit Exits With Code 3

**Requirement:** 16-REQ-4.4
**Type:** unit
**Description:** A cost-limited run exits with code 3.

**Preconditions:**
- Orchestrator mocked to return `ExecutionState` with run_status="cost_limit".

**Input:**
- Invoke `main` with `["code"]`.

**Expected:**
- Exit code 3.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["code"])
ASSERT result.exit_code == 3
```

---

### TS-16-8: Interrupted Execution Exits With Code 130

**Requirement:** 16-REQ-4.5
**Type:** unit
**Description:** An interrupted run exits with code 130.

**Preconditions:**
- Orchestrator mocked to return `ExecutionState` with run_status="interrupted".

**Input:**
- Invoke `main` with `["code"]`.

**Expected:**
- Exit code 130.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["code"])
ASSERT result.exit_code == 130
```

## Edge Case Tests

### TS-16-E1: Missing Plan File

**Requirement:** 16-REQ-1.E1
**Type:** unit
**Description:** The command exits with code 1 when no plan exists.

**Preconditions:**
- No `.agent-fox/plan.json` file.

**Input:**
- Invoke `main` with `["code"]`.

**Expected:**
- Exit code 1.
- Output contains "plan" (error message mentioning plan).

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["code"])
ASSERT result.exit_code == 1
ASSERT "plan" IN result.output.lower()
```

---

### TS-16-E2: Unexpected Exception

**Requirement:** 16-REQ-1.E2
**Type:** unit
**Description:** Unexpected exceptions are caught and reported.

**Preconditions:**
- Orchestrator mocked to raise `RuntimeError("boom")`.

**Input:**
- Invoke `main` with `["code"]`.

**Expected:**
- Exit code 1.
- Output contains "error" (user-friendly message).

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["code"])
ASSERT result.exit_code == 1
ASSERT "error" IN result.output.lower()
```

---

### TS-16-E3: Empty Plan (Zero Tasks)

**Requirement:** 16-REQ-3.E1
**Type:** unit
**Description:** An empty plan prints a message and exits 0.

**Preconditions:**
- Orchestrator mocked to return `ExecutionState` with empty `node_states`
  and run_status="completed".

**Input:**
- Invoke `main` with `["code"]`.

**Expected:**
- Exit code 0.
- Output contains "No tasks to execute."

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["code"])
ASSERT result.exit_code == 0
ASSERT "No tasks to execute" IN result.output
```

---

### TS-16-E4: Unknown Run Status

**Requirement:** 16-REQ-4.E1
**Type:** unit
**Description:** An unrecognized run status exits with code 1.

**Preconditions:**
- Orchestrator mocked to return `ExecutionState` with
  run_status="unknown_status".

**Input:**
- Invoke `main` with `["code"]`.

**Expected:**
- Exit code 1.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["code"])
ASSERT result.exit_code == 1
```

## Property Test Cases

### TS-16-P1: Exit Code Mapping Consistency

**Property:** Property 1 from design.md
**Validates:** 16-REQ-4.1, 16-REQ-4.2, 16-REQ-4.3, 16-REQ-4.4, 16-REQ-4.5, 16-REQ-4.E1
**Type:** property
**Description:** The exit code function always returns the correct mapping.

**For any:** run_status string (from the known set + arbitrary strings)
**Invariant:** The exit code matches the defined mapping, defaulting to 1 for
unknown values.

**Assertion pseudocode:**
```
FOR ANY status IN {"completed", "stalled", "cost_limit", "session_limit",
                   "interrupted", random_strings}:
    code = _exit_code_for_status(status)
    IF status == "completed": ASSERT code == 0
    ELIF status == "stalled": ASSERT code == 2
    ELIF status IN {"cost_limit", "session_limit"}: ASSERT code == 3
    ELIF status == "interrupted": ASSERT code == 130
    ELSE: ASSERT code == 1
```

---

### TS-16-P2: Override Preservation

**Property:** Property 2 from design.md
**Validates:** 16-REQ-2.1, 16-REQ-2.3, 16-REQ-2.4, 16-REQ-2.5
**Type:** property
**Description:** CLI overrides are applied correctly while preserving defaults.

**For any:** combination of parallel (1-8 or None), max_cost (float or None),
max_sessions (int or None)
**Invariant:** The resulting config has overridden fields set to the provided
values, and all other fields identical to the original config.

**Assertion pseudocode:**
```
FOR ANY parallel IN {None, 1..8}, max_cost IN {None, 0.0..1000.0},
       max_sessions IN {None, 1..1000}:
    result = _apply_overrides(default_config, parallel, max_cost, max_sessions)
    IF parallel IS NOT None: ASSERT result.parallel == parallel
    ELSE: ASSERT result.parallel == default_config.parallel
    IF max_cost IS NOT None: ASSERT result.max_cost == max_cost
    ELSE: ASSERT result.max_cost == default_config.max_cost
    ASSERT result.max_retries == default_config.max_retries  # unchanged
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 16-REQ-1.1 | TS-16-1 | unit |
| 16-REQ-1.2 | TS-16-2 | unit |
| 16-REQ-1.3 | TS-16-2 | unit |
| 16-REQ-1.4 | TS-16-2 | unit |
| 16-REQ-1.E1 | TS-16-E1 | unit |
| 16-REQ-1.E2 | TS-16-E2 | unit |
| 16-REQ-2.1 | TS-16-3, TS-16-P2 | unit, property |
| 16-REQ-2.2 | TS-16-3 | unit |
| 16-REQ-2.3 | TS-16-4, TS-16-P2 | unit, property |
| 16-REQ-2.4 | TS-16-5, TS-16-P2 | unit, property |
| 16-REQ-2.5 | TS-16-3, TS-16-4, TS-16-5, TS-16-P2 | unit, property |
| 16-REQ-2.E1 | TS-16-3 | unit |
| 16-REQ-3.1 | TS-16-2 | unit |
| 16-REQ-3.2 | TS-16-2 | unit |
| 16-REQ-3.E1 | TS-16-E3 | unit |
| 16-REQ-4.1 | TS-16-2, TS-16-P1 | unit, property |
| 16-REQ-4.2 | TS-16-E2, TS-16-P1 | unit, property |
| 16-REQ-4.3 | TS-16-6, TS-16-P1 | unit, property |
| 16-REQ-4.4 | TS-16-7, TS-16-P1 | unit, property |
| 16-REQ-4.5 | TS-16-8, TS-16-P1 | unit, property |
| 16-REQ-4.E1 | TS-16-E4, TS-16-P1 | unit, property |
| 16-REQ-5.1 | TS-16-2 | unit |
| 16-REQ-5.2 | TS-16-2 | unit |
| 16-REQ-5.E1 | TS-16-E2 | unit |
| Property 1 | TS-16-P1 | property |
| Property 2 | TS-16-P2 | property |
| Property 3 | TS-16-2 | unit |
