# Codebase Audit: agent-fox-v2

**Date:** 2026-03-10
**Branch:** `develop` (commit `9dfcc09`)
**Baseline:** 1548 tests passing, 2 warnings

---

## Methodology

- Read all 29+ specifications in `.specs/` (prd, requirements, design docs)
- Read all source code in `agent_fox/` (80+ modules)
- Read all tests in `tests/` (167 test files, 1482 test functions)
- Read all ADRs in `docs/adr/`
- Ran full test suite and linter
- Cross-referenced spec requirements against implementation

---

## 1. Critical: Unwired Production Code

These features are fully implemented as library code but never called from the
execution path. The building blocks exist; they just need connecting.

### 1A. Multi-instance dispatch is dead code

**Spec:** 26-REQ-4.1 through 26-REQ-4.E2, 26-REQ-7.x

`NodeSessionRunner` stores `self._instances` (`session_lifecycle.py:111`) but
**never reads it**. Multi-instance dispatch (running N parallel
Skeptic/Verifier sessions) is not wired. The convergence functions
`converge_skeptic()`, `converge_skeptic_records()`, `converge_verifier()`, and
`converge_verifier_records()` in `convergence.py` are **only called from
tests**.

**Impact:** Skeptic/Verifier archetypes always run as a single instance
regardless of `[archetypes.instances]` config settings. The config is accepted
and validated but silently ignored at runtime.

### 1B. Review output parsing is not connected to session execution

**Spec:** 27-REQ-3.x

`parse_review_output()` and `parse_verification_output()` in
`review_parser.py` are defined but **never called from production code**. After
a Skeptic/Verifier session completes, nothing extracts the JSON findings from
the agent response and inserts them into DuckDB.

**Impact:** The structured review records pipeline is inert. DuckDB tables
`review_findings` and `verification_results` are never populated from live
sessions.

### 1C. DB-backed context rendering is never triggered

**Spec:** 27-REQ-5.1, 27-REQ-5.2

`assemble_context()` in `prompt.py` accepts an optional `conn` parameter for
DB-backed rendering of review/verification sections. But `_build_prompts()` in
`session_lifecycle.py:163` calls it **without** passing `conn`, despite
`self._knowledge_db` being available on the runner instance.

**Impact:** Even if review data were in the DB, it would never be included in
session context. Context always falls back to file-based reading.

### 1D. GitHub issue filing is not wired

**Spec:** 26-REQ-8.5, 27-REQ-7.x, 28-REQ-5.x

`file_or_update_issue()` and `format_issue_body_from_findings()` in
`github_issues.py` are **only imported by test files**. No production code
calls them. When a Skeptic blocks or a Verifier fails, no GitHub issue is
created.

**Impact:** The search-before-create idempotent issue filing feature exists in
code but is never exercised.

### Summary of Critical Holes

All four holes are interconnected. The archetype system has the following
intended chain:

```
run N instances --> parse outputs --> converge --> insert to DB --> render in context --> file issues
```

None of these steps are wired into the `NodeSessionRunner.execute()` path. The
session runs with the correct prompt/model/allowlist (that part works) but
treats Skeptic/Verifier exactly like Coder: runs once, doesn't parse output,
doesn't converge, doesn't file issues.

---

## 2. Moderate: Code Smells and Non-Obvious Issues

### 2A. Redundant metric tracking in `session.py`

`_execute_query` maintains both a `_QueryExecutionState` object AND local
variables (`input_tokens`, `output_tokens`, etc.) in `run_session()`. Lines
110-113 initialize local vars that shadow the state object. The timeout/error
handlers read from `execution_state` while the success path reads from the
`result` dict. This double-tracking is fragile and confusing.

### 2B. `run_fix_loop` coroutine never awaited

Two test warnings indicate `run_fix_loop` coroutines are created but never
awaited:

```
RuntimeWarning: coroutine 'run_fix_loop' was never awaited
```

This appears in `test_json_flag.py` and `test_plan.py`. Suggests the fix
command's async execution may have a wiring issue in certain code paths.

### 2C. Runtime `duckdb` import in `prompt.py`

`prompt.py:20` imports `duckdb` at module level with `noqa: F401`. This is
only used for type annotations in function signatures. Should use a
`TYPE_CHECKING` guard instead to avoid loading the heavy `duckdb` C extension
when the DB isn't needed.

### 2D. Error handling in `fox_edit` temp file cleanup

`edit.py:118` uses a ternary expression as a statement:

```python
os.close(fd) if fd >= 0 else None
```

Should be a proper `if` statement. Additionally, the `BaseException` catch on
line 117 is overly broad — it will catch `SystemExit` and `KeyboardInterrupt`,
which should propagate.

### 2E. Harvest race condition with parallel sessions

`harvester.py:63` calls `checkout_branch(repo_root, dev_branch)` which changes
the **main repo's** HEAD to `develop`. If two parallel sessions try to harvest
simultaneously, they will race on the checkout. The parallel runner should
serialize harvest operations (or each harvest should operate in its own
worktree).

### 2F. `_ROLE_TO_ARCHETYPE` mapping is incomplete

`prompt.py:388-391` maps only `"coding"` and `"coordinator"` as legacy roles.
`build_system_prompt` raises `ValueError` for unknown roles. This is not
blocking since the `archetype` parameter takes precedence and is always set by
`session_lifecycle.py`, but the legacy path is fragile.

### 2G. Unused `archetypes.backends` config field

`ArchetypesConfig.backends` (a `dict[str, str]`) is parsed from config and
stored but never consumed anywhere. Only the `"claude"` backend exists, so
this is cosmetic, but it's dead config surface area.

---

## 3. Test Coverage Gaps

### 3A. No integration test for the full archetype lifecycle

Unit tests exist for convergence, review parsing, issue filing, and archetype
resolution individually. But no test verifies the full pipeline: run Skeptic ->
parse output -> converge -> insert to DB -> render in context -> file issue.
This is partly because the pipeline isn't wired (see section 1).

### 3B. Modules without dedicated test imports

| Module | Notes |
|--------|-------|
| `cli/lint_spec.py` | CLI wiring untested; underlying `spec/validator.py` is tested |
| `cli/serve_tools.py` | Click command untested; MCP server has integration test |
| `core/client.py` | Thin factory over SDK types; acceptable |

### 3C. Modules tested only indirectly

These modules have no dedicated unit tests but are covered by integration or
property tests:

- `engine/engine.py` (tested via orchestrator integration tests)
- `session/session.py` (tested via runner property tests)
- `workspace/workspace.py` (tested via workspace integration tests)
- `engine/session_lifecycle.py` (tested via engine tests)
- `knowledge/query.py` (tested via search tests)
- `core/logging.py` (no tests at all)

### 3D. Parallel harvest is untested

No test covers concurrent harvest operations from parallel sessions. This is
where the race condition (2E) would manifest.

### 3E. Mock-heavy engine tests may mask integration issues

The engine tests use `MockSessionRunner` and `MockBackend` extensively. While
this is appropriate for unit tests, the mocking masks the fact that the real
`NodeSessionRunner` doesn't wire multi-instance dispatch — the mock accepts
`instances` but doesn't exercise the full code path.

---

## 4. Documentation and Memory

### 4A. `docs/memory.md` has low signal-to-noise ratio

The memory file is 179 lines of accumulated session observations. Most entries
are obvious software engineering practices (e.g., "Import ordering in Python
test files is subject to linter checks"). The genuinely useful project-specific
entries are buried.

**Recommendation:** Prune to ~30 high-value, project-specific entries.

---

## 5. Ideas: Radical Improvements

### 5A. Wire the archetype pipeline (highest impact fix)

The biggest bang-for-buck change is wiring the four holes in section 1 as one
coherent change. All building blocks exist — they just need connecting:

1. In `_run_and_harvest`: if `self._instances > 1`, run N sessions in parallel
2. Collect agent text output from each session (requires capturing
   `AssistantMessage.content` during streaming)
3. Parse output with `parse_review_output` / `parse_verification_output`
4. Run convergence via `converge_skeptic_records` / `converge_verifier_records`
5. Insert results via `insert_findings` / `insert_verdicts`
6. File GitHub issues on blocking findings
7. Pass `conn` to `assemble_context` for subsequent sessions

This turns the archetype system from "nice prompts with the right model" into
an actual automated quality gate.

### 5B. Simplify the configuration surface

The project has 10 top-level config sections. Several could be merged or
eliminated:

- `memory` has only one field (`model`) — merge into `models`
- `tools` has only one field (`fox_tools`) — merge into a top-level boolean or
  into `orchestrator`
- `theme` defaults work for 99% of users — could be a single
  `theme = "default"` string

### 5C. Differential file context (game-changer for token efficiency)

Instead of feeding the entire spec context for every task group, compute a
diff: what changed since the last successful session? This would dramatically
reduce token usage for retry attempts and sequential task groups. The building
blocks exist (`touched_files` in `SessionRecord`, `get_changed_files` in
workspace).

### 5D. Session replay/debug mode

Add `agent-fox replay <node_id>` that re-assembles the exact prompts for a
given node (from the session history) and displays them without executing. This
would be invaluable for debugging failed sessions — users could see exactly
what context and instructions the agent received.

### 5E. Fox tools as default (not opt-in)

The fox tools are well-implemented and benefit every session through reduced
token usage and hash-verified editing. Making them opt-out instead of opt-in
(`tools.fox_tools = true` by default) would improve token efficiency for all
users immediately with minimal risk.

---

## Recommended Priority Order

| Priority | Item | Section | Effort |
|----------|------|---------|--------|
| 1 | Wire archetype pipeline end-to-end | 1A-1D, 5A | Large |
| 2 | Pass DB conn to `assemble_context` | 1C | Small |
| 3 | Fix harvest race condition for parallel mode | 2E | Medium |
| 4 | Clean up redundant metric tracking | 2A | Small |
| 5 | Fix `BaseException` catch in fox_edit | 2D | Small |
| 6 | Move duckdb import behind TYPE_CHECKING | 2C | Small |
| 7 | Prune `docs/memory.md` | 4A | Small |
| 8 | Add integration test for archetype pipeline | 3A | Medium |
