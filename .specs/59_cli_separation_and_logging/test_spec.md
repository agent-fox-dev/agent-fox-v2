# Test Specification: CLI Separation and Logging Improvements

## Overview

Tests validate command renames, backing module parity, truncation limits, and
progress display formatting. Unit tests use Click's `CliRunner` for CLI
invocations and direct function calls for backing modules. Property tests
use Hypothesis to verify truncation and formatting invariants.

## Test Cases

### TS-59-1: Export Command Replaces Dump (Memory)

**Requirement:** 59-REQ-1.1
**Type:** integration
**Description:** `agent-fox export --memory` produces identical output to the
former `dump --memory`.

**Preconditions:**
- Knowledge store database exists with at least one fact.

**Input:**
- CLI invocation: `export --memory`

**Expected:**
- Exit code 0.
- Memory summary file written to `docs/memory.md`.
- Confirmation message printed to stderr.

**Assertion pseudocode:**
```
result = CliRunner.invoke(main, ["export", "--memory"])
ASSERT result.exit_code == 0
ASSERT Path("docs/memory.md").exists()
```

### TS-59-2: Export Command Replaces Dump (DB)

**Requirement:** 59-REQ-1.2
**Type:** integration
**Description:** `agent-fox export --db` produces identical output to the
former `dump --db`.

**Preconditions:**
- Knowledge store database exists with at least one table.

**Input:**
- CLI invocation: `export --db`

**Expected:**
- Exit code 0.
- Database dump file written.

**Assertion pseudocode:**
```
result = CliRunner.invoke(main, ["export", "--db"])
ASSERT result.exit_code == 0
```

### TS-59-3: Lint-Specs Command Replaces Lint-Spec

**Requirement:** 59-REQ-1.3
**Type:** integration
**Description:** `agent-fox lint-specs` produces identical output to the
former `lint-spec`.

**Preconditions:**
- `.specs/` directory exists with at least one spec.

**Input:**
- CLI invocation: `lint-specs`

**Expected:**
- Findings printed (or "No findings" message).
- Exit code based on finding severity.

**Assertion pseudocode:**
```
result = CliRunner.invoke(main, ["lint-specs"])
ASSERT result.exit_code in (0, 1)
```

### TS-59-4: Lint-Specs Accepts All Original Flags

**Requirement:** 59-REQ-1.4
**Type:** unit
**Description:** `lint-specs --ai --fix --all` is accepted without error.

**Preconditions:**
- `.specs/` directory exists.

**Input:**
- CLI invocation: `lint-specs --all` (--ai and --fix require API access, test
  --all alone for flag acceptance)

**Expected:**
- Command runs without "no such option" error.

**Assertion pseudocode:**
```
result = CliRunner.invoke(main, ["lint-specs", "--all"])
ASSERT "no such option" NOT IN result.output
```

### TS-59-5: Old Command Name "dump" Removed

**Requirement:** 59-REQ-1.E1
**Type:** unit
**Description:** `agent-fox dump` exits with error.

**Preconditions:** None.

**Input:**
- CLI invocation: `dump`

**Expected:**
- Non-zero exit code.
- Error output mentions unknown command.

**Assertion pseudocode:**
```
result = CliRunner.invoke(main, ["dump"])
ASSERT result.exit_code != 0
```

### TS-59-6: Old Command Name "lint-spec" Removed

**Requirement:** 59-REQ-1.E2
**Type:** unit
**Description:** `agent-fox lint-spec` exits with error.

**Preconditions:** None.

**Input:**
- CLI invocation: `lint-spec`

**Expected:**
- Non-zero exit code.

**Assertion pseudocode:**
```
result = CliRunner.invoke(main, ["lint-spec"])
ASSERT result.exit_code != 0
```

### TS-59-7: export_memory Callable From Code

**Requirement:** 59-REQ-2.1
**Type:** unit
**Description:** `export_memory()` can be imported and called directly.

**Preconditions:**
- DuckDB connection with memory_facts table.

**Input:**
- `export_memory(conn, output_path, json_mode=False)`

**Expected:**
- Returns `ExportResult` with count ≥ 0 and output_path set.
- No Click/sys.exit calls.

**Assertion pseudocode:**
```
result = export_memory(conn, tmp_path / "memory.md")
ASSERT isinstance(result, ExportResult)
ASSERT result.count >= 0
ASSERT result.output_path.exists()
```

### TS-59-8: export_db Callable From Code

**Requirement:** 59-REQ-2.2
**Type:** unit
**Description:** `export_db()` can be imported and called directly.

**Preconditions:**
- DuckDB connection with tables.

**Input:**
- `export_db(conn, output_path, json_mode=False)`

**Expected:**
- Returns `ExportResult` with table count.

**Assertion pseudocode:**
```
result = export_db(conn, tmp_path / "dump.md")
ASSERT isinstance(result, ExportResult)
ASSERT result.count >= 0
```

### TS-59-9: export Functions Return Results, Not Print

**Requirement:** 59-REQ-2.3
**Type:** unit
**Description:** Export functions return data instead of printing.

**Preconditions:**
- DuckDB connection.

**Input:**
- `export_memory(conn, path)`

**Expected:**
- No output to stdout/stderr.
- Return value contains count.

**Assertion pseudocode:**
```
with capture_output() as captured:
    result = export_memory(conn, path)
ASSERT captured.stdout == ""
ASSERT result.count >= 0
```

### TS-59-10: run_lint_specs Callable From Code

**Requirement:** 59-REQ-3.1
**Type:** unit
**Description:** `run_lint_specs()` can be imported and called directly.

**Preconditions:**
- `.specs/` directory with at least one spec.

**Input:**
- `run_lint_specs(specs_dir, ai=False, fix=False, lint_all=False)`

**Expected:**
- Returns `LintResult` with findings list and exit code.

**Assertion pseudocode:**
```
result = run_lint_specs(Path(".specs"))
ASSERT isinstance(result, LintResult)
ASSERT isinstance(result.findings, list)
ASSERT result.exit_code in (0, 1)
```

### TS-59-11: run_lint_specs Returns Structured Result

**Requirement:** 59-REQ-3.2
**Type:** unit
**Description:** `run_lint_specs()` returns findings and exit code.

**Preconditions:**
- Spec with a known validation error.

**Input:**
- `run_lint_specs(specs_dir)`

**Expected:**
- `LintResult.findings` is non-empty.
- `LintResult.exit_code` is 1.

**Assertion pseudocode:**
```
result = run_lint_specs(bad_specs_dir)
ASSERT len(result.findings) > 0
ASSERT result.exit_code == 1
```

### TS-59-12: run_lint_specs fix=True Does Not Git Commit

**Requirement:** 59-REQ-3.3
**Type:** unit
**Description:** `run_lint_specs(fix=True)` applies fixes but does not
create git branches or commits.

**Preconditions:**
- Spec with a fixable finding.

**Input:**
- `run_lint_specs(specs_dir, fix=True)`

**Expected:**
- Fix results returned in `LintResult.fix_results`.
- No git commands executed.

**Assertion pseudocode:**
```
with patch("subprocess.run") as mock_run:
    result = run_lint_specs(specs_dir, fix=True)
ASSERT mock_run not called with ["git", ...]
ASSERT len(result.fix_results) >= 0
```

### TS-59-13: run_lint_specs Raises on Missing Dir

**Requirement:** 59-REQ-3.E1
**Type:** unit
**Description:** `run_lint_specs()` raises `PlanError` when specs_dir is
missing.

**Preconditions:**
- specs_dir does not exist.

**Input:**
- `run_lint_specs(Path("/nonexistent"))`

**Expected:**
- `PlanError` raised.

**Assertion pseudocode:**
```
ASSERT_RAISES PlanError:
    run_lint_specs(Path("/nonexistent"))
```

### TS-59-14: run_code Callable From Code

**Requirement:** 59-REQ-4.1
**Type:** unit
**Description:** `run_code()` can be imported and called with explicit
parameters.

**Preconditions:**
- Valid AgentFoxConfig.

**Input:**
- `run_code(config, parallel=2, max_cost=1.0)`

**Expected:**
- Returns `ExecutionState`.
- Orchestrator receives parallel=2 and max_cost=1.0.

**Assertion pseudocode:**
```
with patch("agent_fox.engine.run.Orchestrator") as MockOrch:
    MockOrch.return_value.run = AsyncMock(return_value=mock_state)
    result = await run_code(config, parallel=2, max_cost=1.0)
ASSERT isinstance(result, ExecutionState)
```

### TS-59-15: run_code Returns ExecutionState

**Requirement:** 59-REQ-4.2
**Type:** unit
**Description:** `run_code()` returns an `ExecutionState` with status.

**Preconditions:**
- Mocked orchestrator.

**Input:**
- `run_code(config)`

**Expected:**
- `ExecutionState` with status field.

**Assertion pseudocode:**
```
result = await run_code(config)
ASSERT result.status in ("completed", "stalled", "cost_limit", ...)
```

### TS-59-15b: run_code Passes Parallelism Override

**Requirement:** 59-REQ-4.3
**Type:** unit
**Description:** `run_code(config, parallel=4)` passes parallelism to
orchestrator config.

**Preconditions:**
- Mocked orchestrator.

**Input:**
- `run_code(config, parallel=4)`

**Expected:**
- Orchestrator receives parallel=4 in its config.

**Assertion pseudocode:**
```
with patch("agent_fox.engine.run.Orchestrator") as MockOrch:
    MockOrch.return_value.run = AsyncMock(return_value=mock_state)
    await run_code(config, parallel=4)
ASSERT MockOrch.call_args contains parallel=4
```

### TS-59-16: run_code Handles KeyboardInterrupt

**Requirement:** 59-REQ-4.E1
**Type:** unit
**Description:** KeyboardInterrupt during `run_code` returns interrupted state.

**Preconditions:**
- Orchestrator raises KeyboardInterrupt.

**Input:**
- `run_code(config)` with mocked orchestrator that raises.

**Expected:**
- Returns `ExecutionState` with status `"interrupted"`.

**Assertion pseudocode:**
```
with patch(..., side_effect=KeyboardInterrupt):
    result = await run_code(config)
ASSERT result.status == "interrupted"
```

### TS-59-17: Remaining Commands Have Backing Functions

**Requirement:** 59-REQ-5.1
**Type:** unit
**Description:** All 6 remaining commands have importable backing functions.

**Preconditions:** None.

**Input:**
- Import each backing function.

**Expected:**
- All are callable.

**Assertion pseudocode:**
```
from agent_fox.fix.runner import run_fix
from agent_fox.graph.planner import run_plan
from agent_fox.engine.reset import run_reset
from agent_fox.workspace.init_project import init_project
from agent_fox.reporting.status import generate_status
from agent_fox.reporting.standup import generate_standup
ASSERT all are callable
```

### TS-59-18: Backing Functions Accept Explicit Parameters

**Requirement:** 59-REQ-5.2
**Type:** unit
**Description:** Backing function signatures match CLI options.

**Preconditions:** None.

**Input:**
- Inspect each function's signature.

**Expected:**
- Parameters match the corresponding CLI command's options.

**Assertion pseudocode:**
```
sig = inspect.signature(run_fix)
ASSERT "issue_url" in sig.parameters
ASSERT "max_attempts" in sig.parameters
```

### TS-59-19: Backing Functions Return Results

**Requirement:** 59-REQ-5.3
**Type:** unit
**Description:** Backing functions return structured results, not None.

**Preconditions:** None.

**Input:**
- Call `generate_status(config)`.

**Expected:**
- Returns a StatusReport (not None, not printed to stdout).

**Assertion pseudocode:**
```
result = generate_status(config)
ASSERT result is not None
```

### TS-59-20: Truncation Default Is 60

**Requirement:** 59-REQ-6.1
**Type:** unit
**Description:** `abbreviate_arg` default max_len is 60.

**Preconditions:** None.

**Input:**
- `abbreviate_arg("a" * 80)`

**Expected:**
- Result length ≤ 60.

**Assertion pseudocode:**
```
result = abbreviate_arg("a" * 80)
ASSERT len(result) <= 60
```

### TS-59-21: Path Truncation at 60 Characters

**Requirement:** 59-REQ-6.2
**Type:** unit
**Description:** Long file paths are truncated with `…/` prefix at 60 chars.

**Preconditions:** None.

**Input:**
- `abbreviate_arg("/very/long/path/to/some/deeply/nested/directory/structure/file.py")`

**Expected:**
- Result length ≤ 60.
- Result starts with `…/` or contains trailing path components.

**Assertion pseudocode:**
```
result = abbreviate_arg("/very/long/path/.../file.py")
ASSERT len(result) <= 60
ASSERT "file.py" in result
```

### TS-59-22: Task Line Includes Archetype on Complete

**Requirement:** 59-REQ-7.1
**Type:** unit
**Description:** Completed task line includes `[archetype]`.

**Preconditions:** None.

**Input:**
- `TaskEvent(node_id="spec:1", status="completed", duration_s=45.0, archetype="coder")`

**Expected:**
- Formatted line contains `[coder]`.

**Assertion pseudocode:**
```
line = progress._format_task_line(event)
ASSERT "[coder]" in str(line)
ASSERT "done" in str(line)
```

### TS-59-23: Task Line Includes Archetype on Failure

**Requirement:** 59-REQ-7.2
**Type:** unit
**Description:** Failed task line includes `[archetype]`.

**Preconditions:** None.

**Input:**
- `TaskEvent(node_id="spec:1", status="failed", duration_s=0, archetype="verifier")`

**Expected:**
- Formatted line contains `[verifier]` and `failed`.

**Assertion pseudocode:**
```
line = progress._format_task_line(event)
ASSERT "[verifier]" in str(line)
```

### TS-59-24: Task Line Omits Archetype When None

**Requirement:** 59-REQ-7.E1
**Type:** unit
**Description:** When archetype is None, bracket label is omitted.

**Preconditions:** None.

**Input:**
- `TaskEvent(node_id="spec:1", status="completed", duration_s=10, archetype=None)`

**Expected:**
- Formatted line does not contain `[`.

**Assertion pseudocode:**
```
line = progress._format_task_line(event)
ASSERT "[" not in str(line) or only "[" from node_id format
```

### TS-59-25: Disagreement Line Format

**Requirement:** 59-REQ-8.1
**Type:** unit
**Description:** Reviewer disagreement produces correct permanent line.

**Preconditions:** None.

**Input:**
- `TaskEvent(node_id="spec:0", status="disagreed", duration_s=0, archetype="skeptic", predecessor_node="spec:1")`

**Expected:**
- Line contains `✗`, `[skeptic]`, `disagrees`, `→ retry spec:1`.

**Assertion pseudocode:**
```
line = progress._format_task_line(event)
text = str(line)
ASSERT "[skeptic]" in text
ASSERT "disagrees" in text
ASSERT "spec:1" in text
```

### TS-59-26: Retry Line Format

**Requirement:** 59-REQ-8.2
**Type:** unit
**Description:** Retry event produces correct permanent line.

**Preconditions:** None.

**Input:**
- `TaskEvent(node_id="spec:1", status="retry", duration_s=0, archetype="coder", attempt=2)`

**Expected:**
- Line contains `⟳`, `[coder]`, `retry #2`.

**Assertion pseudocode:**
```
line = progress._format_task_line(event)
text = str(line)
ASSERT "retry #2" in text
ASSERT "[coder]" in text
```

### TS-59-27: Retry With Escalation Line Format

**Requirement:** 59-REQ-8.3
**Type:** unit
**Description:** Retry with escalation includes model tier info.

**Preconditions:** None.

**Input:**
- `TaskEvent(node_id="spec:1", status="retry", duration_s=0, archetype="coder", attempt=2, escalated_from="STANDARD", escalated_to="ADVANCED")`

**Expected:**
- Line contains `escalated: STANDARD → ADVANCED`.

**Assertion pseudocode:**
```
line = progress._format_task_line(event)
text = str(line)
ASSERT "escalated: STANDARD" in text
ASSERT "ADVANCED" in text
```

### TS-59-28: Retry Without Escalation Omits Suffix

**Requirement:** 59-REQ-8.E1
**Type:** unit
**Description:** Retry without escalation omits escalation suffix.

**Preconditions:** None.

**Input:**
- `TaskEvent(node_id="spec:1", status="retry", duration_s=0, archetype="coder", attempt=2, escalated_from=None)`

**Expected:**
- Line contains `retry #2` but NOT `escalated`.

**Assertion pseudocode:**
```
line = progress._format_task_line(event)
text = str(line)
ASSERT "retry #2" in text
ASSERT "escalated" not in text
```

### TS-59-29: CLI Handlers Delegate to Backing Functions

**Requirement:** 59-REQ-9.1
**Type:** unit
**Description:** CLI handlers contain no business logic.

**Preconditions:** None.

**Input:**
- Read source of each CLI handler.

**Expected:**
- Each handler calls exactly one backing function.
- No direct database queries, file parsing, or computation in handler.

**Assertion pseudocode:**
```
source = inspect.getsource(export_cmd)
ASSERT "export_memory(" in source or "export_db(" in source
ASSERT "conn.execute" not in source
```

### TS-59-30: CLI Handlers Pass Options as Parameters

**Requirement:** 59-REQ-9.2
**Type:** unit
**Description:** CLI handlers pass options as explicit parameters.

**Preconditions:** None.

**Input:**
- Read source of lint-specs handler.

**Expected:**
- Backing function called with named parameters matching CLI options.

**Assertion pseudocode:**
```
source = inspect.getsource(lint_specs_cmd)
ASSERT "run_lint_specs(" in source
ASSERT "ai=" in source or "ai" appears as kwarg
```

## Property Test Cases

### TS-59-P1: Truncation Length Invariant

**Property:** Property 1 from design.md
**Validates:** 59-REQ-6.1, 59-REQ-6.2
**Type:** property
**Description:** `abbreviate_arg` output never exceeds max_len.

**For any:** string of length 0–500, max_len of 10–200
**Invariant:** `len(abbreviate_arg(s, max_len)) <= max_len`

**Assertion pseudocode:**
```
FOR ANY s IN text(max_size=500), max_len IN integers(10, 200):
    result = abbreviate_arg(s, max_len)
    ASSERT len(result) <= max_len
```

### TS-59-P2: Archetype Label Presence

**Property:** Property 2 from design.md
**Validates:** 59-REQ-7.1, 59-REQ-7.2, 59-REQ-7.3
**Type:** property
**Description:** TaskEvent with archetype always produces a line containing
`[{archetype}]`.

**For any:** archetype in known archetype set, status in
{"completed", "failed", "blocked"}
**Invariant:** `f"[{archetype}]"` appears in the formatted line.

**Assertion pseudocode:**
```
FOR ANY archetype IN sampled_from(ARCHETYPES), status IN sampled_from(STATUSES):
    event = TaskEvent(node_id="s:1", status=status, duration_s=1.0, archetype=archetype)
    line = format_task_line(event)
    ASSERT f"[{archetype}]" in str(line)
```

### TS-59-P3: Event Line Format Correctness

**Property:** Property 3 from design.md
**Validates:** 59-REQ-8.2, 59-REQ-8.3, 59-REQ-8.E1
**Type:** property
**Description:** Retry events always include attempt number; escalation
info only when escalated_from is set.

**For any:** attempt in 1–10, escalated_from in {None, "SIMPLE", "STANDARD"}
**Invariant:** `retry #{attempt}` always present; `escalated:` present iff
escalated_from is not None.

**Assertion pseudocode:**
```
FOR ANY attempt IN integers(1, 10), esc IN sampled_from([None, "SIMPLE", "STANDARD"]):
    event = TaskEvent(
        node_id="s:1", status="retry", duration_s=0,
        archetype="coder", attempt=attempt,
        escalated_from=esc, escalated_to="ADVANCED" if esc else None,
    )
    line = str(format_task_line(event))
    ASSERT f"retry #{attempt}" in line
    ASSERT ("escalated:" in line) == (esc is not None)
```

## Edge Case Tests

Edge cases are covered by the primary test cases above:

- 59-REQ-1.E1 → TS-59-5
- 59-REQ-1.E2 → TS-59-6
- 59-REQ-3.E1 → TS-59-13
- 59-REQ-4.E1 → TS-59-16
- 59-REQ-7.E1 → TS-59-24
- 59-REQ-8.E1 → TS-59-28

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 59-REQ-1.1 | TS-59-1 | integration |
| 59-REQ-1.2 | TS-59-2 | integration |
| 59-REQ-1.3 | TS-59-3 | integration |
| 59-REQ-1.4 | TS-59-4 | unit |
| 59-REQ-1.E1 | TS-59-5 | unit |
| 59-REQ-1.E2 | TS-59-6 | unit |
| 59-REQ-2.1 | TS-59-7 | unit |
| 59-REQ-2.2 | TS-59-8 | unit |
| 59-REQ-2.3 | TS-59-9 | unit |
| 59-REQ-3.1 | TS-59-10 | unit |
| 59-REQ-3.2 | TS-59-11 | unit |
| 59-REQ-3.3 | TS-59-12 | unit |
| 59-REQ-3.E1 | TS-59-13 | unit |
| 59-REQ-4.1 | TS-59-14 | unit |
| 59-REQ-4.2 | TS-59-15 | unit |
| 59-REQ-4.3 | TS-59-15b | unit |
| 59-REQ-4.E1 | TS-59-16 | unit |
| 59-REQ-5.1 | TS-59-17 | unit |
| 59-REQ-5.2 | TS-59-18 | unit |
| 59-REQ-5.3 | TS-59-19 | unit |
| 59-REQ-6.1 | TS-59-20 | unit |
| 59-REQ-6.2 | TS-59-21 | unit |
| 59-REQ-7.1 | TS-59-22 | unit |
| 59-REQ-7.2 | TS-59-23 | unit |
| 59-REQ-7.3 | TS-59-24 | unit |
| 59-REQ-7.E1 | TS-59-24 | unit |
| 59-REQ-8.1 | TS-59-25 | unit |
| 59-REQ-8.2 | TS-59-26 | unit |
| 59-REQ-8.3 | TS-59-27 | unit |
| 59-REQ-8.E1 | TS-59-28 | unit |
| 59-REQ-9.1 | TS-59-29 | unit |
| 59-REQ-9.2 | TS-59-30 | unit |
| Property 1 | TS-59-P1 | property |
| Property 2 | TS-59-P2 | property |
| Property 3 | TS-59-P3 | property |
