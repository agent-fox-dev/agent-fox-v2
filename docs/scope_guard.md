# Scope Guard

Scope Guard prevents wasted coder sessions by detecting already-complete work
before launching agents and enforcing stub-only output from test-writing
sessions. It comprises four interlocking subsystems.

## Subsystems

### 1. Stub Enforcement

Test-writing task groups must produce only type signatures and stub bodies in
non-test code. After a session completes, the stub validator scans all modified
non-test source files and flags any function body that contains real
implementation logic.

**Supported languages and stub patterns:**

| Language | Recognized Stubs |
|---|---|
| Rust | `todo!()`, `unimplemented!()`, `panic!("not implemented")` |
| Python | `raise NotImplementedError`, `pass` (sole body) |
| TypeScript/JS | `throw new Error("not implemented")` |

A function body qualifies as a stub only if, after stripping comments and
whitespace, it consists entirely of a single recognized placeholder. Additional
statements (even alongside a stub placeholder) disqualify the body.

**Test block exclusion:** Functions inside test-attributed blocks
(`#[cfg(test)]` in Rust, `test_*` files/functions in Python,
`*.test.*`/`*.spec.*` files in TS/JS) are excluded from enforcement.

**Unsupported languages:** Files in languages outside the supported set are
skipped with a warning and listed in the validation result.

### 2. Pre-Flight Scope Checking

Before launching a coder session, the system compares each deliverable in the
task group against the current codebase:

- **Pending** -- function body is a stub or does not exist yet.
- **Already implemented** -- function body has substantive logic.
- **Indeterminate** -- file cannot be parsed or deliverables are not enumerated.

**Outcomes:**

| Scope Check Result | Action |
|---|---|
| All implemented | Skip session (pre-flight-skip, zero cost) |
| Partially implemented | Launch with reduced scope (pending items only) |
| All pending / indeterminate | Launch full session |

Duration, deliverable count, and per-deliverable status are logged to the
telemetry store after every check.

### 3. Scope Overlap Detection

When a specification graph is finalized, the overlap detector compares
deliverable lists across all task groups:

- Overlap is identified when two or more task groups list the same
  `(file_path, function_id)` pair.
- Same file but different functions is **not** an overlap.
- Overlaps between task groups **with** a dependency relationship produce a
  **warning** (the downstream pre-flight check handles it).
- Overlaps between task groups **without** a dependency relationship produce an
  **error** that blocks execution.
- Task groups with empty deliverable lists are excluded from analysis.
- Graphs with zero or one task groups skip detection entirely.

### 4. No-Op Completion Tracking

Session outcomes are classified into mutually exclusive categories:

| Classification | Condition |
|---|---|
| `success` | Session produced functional commits |
| `no-op` | Zero functional commits, normal exit (work already done) |
| `pre-flight-skip` | Skipped by pre-flight check (all deliverables implemented) |
| `failure` | Session ended in error/timeout |
| `harvest-error` | Could not determine commit count (git error) |

Whitespace-only or comment-only commits are treated as no functional commits
(session classified as no-op).

## Telemetry

All session outcomes, prompts, and scope check results are stored in DuckDB.

**Tables:**

- `session_outcomes` -- one row per session with classification, cost, duration.
- `session_prompts` -- full prompt text (truncated if > 100K chars).
- `scope_check_results` -- per-deliverable status from pre-flight checks.

**Waste reporting:** `query_waste_report()` returns per-specification aggregates
of no-op and pre-flight-skip counts, wasted cost, and wasted duration.

## Prompt Directive

Test-writing sessions receive a machine-parseable stub constraint directive:

```
<!-- SCOPE_GUARD:STUB_ONLY -->
CONSTRAINT: For all non-test source code, produce ONLY type signatures
and stub bodies...
<!-- /SCOPE_GUARD:STUB_ONLY -->
```

The presence of `SCOPE_GUARD:STUB_ONLY` tags is checked during violation
analysis to distinguish "constraint missing from prompt" from "agent ignored
constraint."

## Configuration Flags

Each subsystem can be independently enabled or disabled:

- `SCOPE_GUARD_STUB_VALIDATION_ENABLED` (default: `true`)
- `SCOPE_GUARD_PREFLIGHT_ENABLED` (default: `true`)
- `SCOPE_GUARD_OVERLAP_DETECTION_ENABLED` (default: `true`)
- `SCOPE_GUARD_OVERLAP_BLOCKING_ENABLED` (default: `true`)

## Module Layout

```
agent_fox/scope_guard/
  __init__.py          -- public API exports
  models.py            -- data models, enums, typed structures
  stub_patterns.py     -- language-specific stub/test-block patterns
  source_parser.py     -- function boundary extraction (regex-based)
  stub_validator.py    -- post-session stub enforcement validation
  preflight_checker.py -- pre-flight scope checking
  overlap_detector.py  -- specification graph overlap detection
  prompt_builder.py    -- coder session prompt construction
  session_classifier.py-- session outcome classification
  telemetry.py         -- DuckDB persistence and waste reporting
```
