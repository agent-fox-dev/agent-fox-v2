# Consolidated Audit Report: agent-fox-v2

**Date:** 2026-03-10
**Branch:** `develop` (commit `9dfcc09`)
**Auditors:** Cursor, Codex, Claude, Kiro
**Baseline:** ~1548 tests passing, 2-3 warnings, 4-13 lint issues

---

## How to Read This Document

Each finding lists which auditors reported it. Findings confirmed by multiple
auditors are marked with the count (e.g. **[3/4]**). Unique findings discovered
by only one auditor are marked **[1/4]**.

Items are split into two action categories:
- **Directly fixable** — can be fixed now without design decisions or new specs
- **Needs exploration** — requires design decisions, new specs, or further investigation

Feature suggestions are in a separate section at the end.

---

## 1. Bugs

### BUG-1. Fox tools never reach the Claude backend — HIGH [3/4]

**Reported by:** Cursor (B2), Codex (P0), Claude (implied by fox tools wiring analysis)

`session.py` builds fox tool definitions and passes them via
`backend.execute(..., tools=fox_tools)`. `ClaudeBackend.execute` accepts the
`tools` parameter but **never forwards it** to `ClaudeCodeOptions`. The entire
spec-29 in-process fox-tools feature is non-functional. The MCP server path
works correctly.

**File:** `agent_fox/session/backends/claude.py:97-103`
**Action:** Directly fixable — forward `tools` to SDK options.

---

### BUG-2. `reset.py` branch name format mismatch — HIGH [1/4]

**Reported by:** Cursor (B1)

`_task_id_to_branch_name` (line 98) produces `feature/{spec}-{group}` (hyphen),
but `workspace.py:create_worktree` uses `feature/{spec}/{group}` (slash). The
reset command will never delete the correct feature branch.

**File:** `agent_fox/engine/reset.py:98`
**Action:** Directly fixable — change hyphen to slash separator.

---

### BUG-3. JSON error envelope emits command name instead of error message — MEDIUM [1/4]

**Reported by:** Codex (P1)

In `cli/app.py`, `BannerGroup.invoke()` catches `click.ClickException` and
calls `emit_error(str(ctx.invoked_subcommand or "unknown"))` — emitting the
subcommand name (e.g. `"lint-spec"`) instead of the actual exception message.

**File:** `agent_fox/cli/app.py`
**Action:** Directly fixable — emit `str(exc)` instead of subcommand name.

---

### BUG-4. `_build_fix_session_runner` wrong return type annotation — MEDIUM [1/4]

**Reported by:** Cursor (B3)

Annotated as `-> TerminationReason | None` but actually returns an async
callable. The `# type: ignore[return-value]` on line 63 hides the real error.

**File:** `agent_fox/cli/fix.py:31-63`
**Action:** Directly fixable — correct the type annotation.

---

### BUG-5. `run_fix_loop` coroutine never awaited — MEDIUM [1/4]

**Reported by:** Claude (2B)

Two test warnings: `RuntimeWarning: coroutine 'run_fix_loop' was never awaited`
in `test_json_flag.py` and `test_plan.py`. Suggests the fix command's async
execution has a wiring issue in certain code paths.

**Action:** Directly fixable — investigate and await the coroutine.

---

### BUG-6. Banner styling tests fail — LOW [1/4]

**Reported by:** Cursor (B4)

Three tests expect ANSI escape codes but `Console` is not emitting them in the
test environment. Likely a `force_terminal=True` or `color_system` issue.

**Files:** `tests/unit/ui/test_banner.py` (lines 173, 188, 200)
**Action:** Directly fixable — fix test fixture configuration.

---

## 2. Unwired / Dead Code

### DEAD-1. Archetype pipeline is completely unwired — CRITICAL [3/4]

**Reported by:** Claude (1A-1D), Kiro (gap #1), Cursor (H2 partial)

The entire archetype pipeline is implemented as library code but never called
from the execution path. The intended chain:

```
run N instances → parse outputs → converge → insert to DB → render in context → file issues
```

None of these steps are wired into `NodeSessionRunner.execute()`. Specifically:

| Component | Status | Auditors |
|-----------|--------|----------|
| Multi-instance dispatch (`self._instances` stored, never read) | Dead code | Claude |
| `parse_review_output()` / `parse_verification_output()` | Never called from production | Claude |
| `assemble_context(conn=...)` DB parameter | Never passed despite DB being available | Claude |
| `file_or_update_issue()` | Only imported by tests | Claude, Kiro |
| `converge_skeptic()` / `converge_verifier()` | Only called from tests | Claude |

**Impact:** Skeptic/Verifier archetypes run as single instances, don't parse
output, don't converge, don't file issues. Config is accepted but silently
ignored.

**Action:** Needs exploration — large wiring change, may need a corrective spec.

---

### DEAD-2. `plan --verify` prints "not yet implemented" — MEDIUM [1/4]

**Reported by:** Cursor (H1)

The `--verify` flag exists in the CLI but does nothing (spec 02-REQ-7.5).

**File:** `cli/plan.py:197-199`
**Action:** Directly fixable — implement or remove.

---

### DEAD-3. `ask`, `patterns`, `compact` CLI commands are unwired — MEDIUM [2/4]

**Reported by:** Cursor (H2), Codex (P1 — spec governance drift)

Documented as intentionally unwired in `docs/errata/unwired_cli_commands.md`.
Backing modules are maintained and tested without production entry points. Spec
23 still references these commands, creating a governance conflict.

**Action:** Needs exploration — decide whether to wire, remove, or formally
supersede via a numbered spec.

---

### DEAD-4. `Orchestrator._get_predecessors` uses private `GraphSync._edges` — LOW [1/4]

**Reported by:** Cursor (H3)

Accesses a private attribute instead of a public API.

**Action:** Directly fixable — add `GraphSync.predecessors()` method.

---

### DEAD-5. `first_dispatch` unused in parallel mode — LOW [1/4]

**Reported by:** Cursor (H4)

Parameter passed to `_dispatch_parallel` but never referenced.

**Action:** Directly fixable — remove unused parameter.

---

### DEAD-6. Unused `archetypes.backends` config field — LOW [1/4]

**Reported by:** Claude (2G)

`ArchetypesConfig.backends` is parsed and stored but never consumed.

**Action:** Directly fixable — remove dead config field.

---

## 3. Code Smells

### SMELL-1. `spec/validator.py` is 1700+ lines with two import sections — HIGH [2/4]

**Reported by:** Cursor (S1), Codex (P2)

The AI validation logic was appended at line 1634 with its own imports, aliased
to avoid name collisions (`_logging_ai`, `_re_ai`, `_defaultdict_ai`). This
causes ruff E402/F811 errors.

**Action:** Directly fixable — extract into `spec/ai_validator.py`.

---

### SMELL-2. Harvest race condition with parallel sessions — HIGH [2/4]

**Reported by:** Claude (2E), Kiro (gap #6)

`harvester.py:63` calls `checkout_branch(repo_root, dev_branch)` which changes
the main repo's HEAD. Parallel sessions will race on the checkout.

**Action:** Needs exploration — serialize harvest operations or use per-harvest
worktrees.

---

### SMELL-3. Configuration sprawl (10 nested config sections) — MEDIUM [2/4]

**Reported by:** Claude (5B), Kiro (smell #5)

10 top-level config sections with 40+ fields total. Several single-field
sections (`memory`, `tools`) could be merged.

**Action:** Needs exploration — design a simplified config structure.

---

### SMELL-4. Orchestrator is a god object — MEDIUM [1/4]

**Reported by:** Kiro (smell #1)

600+ lines, 20+ methods mixing scheduling, state management, sync barriers,
hot-loading, cost tracking, and signal handling.

**Action:** Needs exploration — extract into focused classes.

---

### SMELL-5. Dual memory systems (JSONL + DuckDB) unclear relationship — MEDIUM [1/4]

**Reported by:** Kiro (smell #2)

Both store facts with different schemas. Unclear which is source of truth.

**Action:** Needs exploration — document or consolidate relationship.

---

### SMELL-6. Silent failures hide degraded features — MEDIUM [1/4]

**Reported by:** Kiro (smell #3)

Knowledge store, hooks, and other subsystems return `None` on failure and
continue silently. Users don't know features are disabled.

**Action:** Needs exploration — add degradation reporting to status output.

---

### SMELL-7. Redundant metric tracking in `session.py` — MEDIUM [1/4]

**Reported by:** Claude (2A)

`_execute_query` maintains both a `_QueryExecutionState` object AND local
variables. Double-tracking is fragile.

**Action:** Directly fixable — consolidate to single tracking path.

---

### SMELL-8. Duplicate tool schemas between registry and MCP server — LOW [2/4]

**Reported by:** Cursor (S5), Claude (implied by single source of truth design)

Tool definitions in `tools/registry.py` and `tools/server.py` define the same
schemas independently.

**Action:** Directly fixable — share schema definitions from one source.

---

### SMELL-9. `NodeTiming.float` shadows Python builtin — MEDIUM [1/4]

**Reported by:** Cursor (S2)

`graph/resolver.py:192` defines a field `float: int`.

**Action:** Directly fixable — rename to `slack` or `total_float`.

---

### SMELL-10. Hardcoded paths scattered across CLI commands — MEDIUM [1/4]

**Reported by:** Cursor (S3)

`.agent-fox`, `.specs`, `plan.json`, `state.jsonl`, etc. hardcoded in multiple
files.

**Action:** Directly fixable — create `core/paths.py` constants module.

---

### SMELL-11. `github_issues.py` exception handling too narrow — MEDIUM [1/4]

**Reported by:** Cursor (S4)

Docstring says failures should never propagate, but only `IntegrationError` is
caught. Other exceptions (`httpx.HTTPError`, `KeyError`) would escape.

**Action:** Directly fixable — broaden the catch.

---

### SMELL-12. Runtime `duckdb` import in `prompt.py` — LOW [1/4]

**Reported by:** Claude (2C)

Module-level `import duckdb` is only used for type annotations. Should use
`TYPE_CHECKING` guard to avoid loading the heavy C extension unnecessarily.

**Action:** Directly fixable.

---

### SMELL-13. `BaseException` catch in `fox_edit` — LOW [1/4]

**Reported by:** Claude (2D)

Catches `BaseException` including `SystemExit` and `KeyboardInterrupt`. Also
uses ternary expression as statement.

**File:** `agent_fox/tools/edit.py:117-118`
**Action:** Directly fixable — narrow to `Exception`, use proper `if`.

---

### SMELL-14. Incomplete `_ROLE_TO_ARCHETYPE` mapping — LOW [1/4]

**Reported by:** Claude (2F)

Maps only `"coding"` and `"coordinator"`. The legacy path raises `ValueError`
for unknown roles.

**Action:** Directly fixable — add remaining mappings or remove legacy path.

---

### SMELL-15. Redundant exception catch in `integration.py` — LOW [1/4]

**Reported by:** Cursor (H5)

`(IntegrationError, Exception)` — `IntegrationError` is already a subclass of
`Exception`.

**Action:** Directly fixable — remove redundant type from catch.

---

### SMELL-16. Permission gating weak for custom tools — MEDIUM [1/4]

**Reported by:** Codex (P2)

`security.py` allows all non-`Bash` tools by default. Custom tools bypass
meaningful policy checks.

**Action:** Needs exploration — decide on deliberate policy and document it.

---

### SMELL-17. `lint-spec --fix` has surprising side effects — MEDIUM [1/4]

**Reported by:** Codex (P2)

A lint/fix command creates branches and commits automatically. Surprising
behavior in automation contexts.

**Action:** Needs exploration — affirm as policy or add `--no-commit` flag.

---

## 4. Lint / Hygiene

### LINT-1. ruff reports 4-13 errors [2/4]

**Reported by:** Cursor (13 errors), Kiro (4 issues)

| File | Rule | Description |
|------|------|-------------|
| `cli/plan.py` | I001 | Unsorted import block |
| `fix/__init__.py` | I001 | Unsorted import block |
| `reporting/standup.py` | E501 | Line too long |
| `spec/validator.py` | E402/F811 | Mid-file imports and redefinitions |

**Action:** Directly fixable — `ruff check --fix` for most, manual fix for
`spec/validator.py` (see SMELL-1).

---

## 5. Spec Compliance Issues

### SPEC-1. Spec 29 (fox tools in sessions) non-functional [3/4]

**Reported by:** Cursor, Codex, Claude

Due to BUG-1, the in-process session path for fox tools doesn't work.
29-REQ-6.2, 29-REQ-6.3, 29-REQ-8.2 are unmet.

**Action:** Directly fixable — fix BUG-1.

---

### SPEC-2. Spec 02 `--verify` unimplemented [1/4]

**Reported by:** Cursor

02-REQ-7.5 is a placeholder.

**Action:** Directly fixable — implement or remove and update spec.

---

### SPEC-3. Spec/errata governance drift for removed CLI commands [1/4]

**Reported by:** Codex (P1)

Spec 23 requires JSON behavior for `ask`, `patterns`, `compact`, `ingest`, but
these commands are removed per `docs/errata/unwired_cli_commands.md`. No
numbered successor spec formally supersedes these requirements.

**Action:** Needs exploration — add a superseding spec or formal amendment.

---

### SPEC-4. Embedding model drift (voyage-3 vs sentence-transformers) [1/4]

**Reported by:** audit-report.md (spec compliance scan)

Spec 12-REQ-2.1 specifies Anthropic voyage-3 (1024 dims); code uses local
`all-MiniLM-L6-v2` (384 dims). This was an intentional improvement.

**Action:** Directly fixable — update spec to match implementation.

---

## 6. Test Coverage Gaps

### TEST-1. No integration test for archetype lifecycle — HIGH [3/4]

**Reported by:** Claude (3A), Kiro (gap #1), Cursor (missing integration tests)

No test verifies: Skeptic → parse → converge → DB → context → issue filing.
Partly because the pipeline isn't wired (DEAD-1).

**Action:** Needs exploration — blocked by DEAD-1 wiring.

---

### TEST-2. `engine/session_lifecycle.py` untested — HIGH [2/4]

**Reported by:** Cursor, Claude (3C)

Core lifecycle orchestration has no dedicated unit tests; only covered
indirectly via engine integration tests.

**Action:** Directly fixable — add unit tests.

---

### TEST-3. `engine/reset.py` untested — HIGH [1/4]

**Reported by:** Cursor

Contains the branch name bug (BUG-2) which would have been caught by tests.

**Action:** Directly fixable — add unit tests.

---

### TEST-4. Backend tests are placeholder/structural — MEDIUM [2/4]

**Reported by:** Codex (P3), Claude (3E)

`test_claude.py` contains "will be implemented" comments. Tests assert
importability rather than behavior.

**Action:** Directly fixable — add behavior-driven tests.

---

### TEST-5. No integration test for main CLI commands — MEDIUM [1/4]

**Reported by:** Cursor

`code`, `fix`, `status`, `standup`, `reset` have no integration tests.

**Action:** Needs exploration — requires test infrastructure for CLI smoke tests.

---

### TEST-6. Parallel execution / harvest race untested — MEDIUM [2/4]

**Reported by:** Claude (3D), Kiro (gap #2)

No test covers concurrent harvest operations or parallel state corruption.

**Action:** Needs exploration — blocked partly by SMELL-2 design decision.

---

### TEST-7. Knowledge store failure modes untested — MEDIUM [1/4]

**Reported by:** Kiro (gap #4)

No tests for DuckDB corruption recovery, JSONL/DuckDB consistency, embedding
generation failure.

**Action:** Directly fixable — add failure-mode tests.

---

### TEST-8. Hot-loading not integration-tested — MEDIUM [1/4]

**Reported by:** Kiro (gap #7), Cursor (untested modules)

No integration test for adding specs mid-execution.

**Action:** Needs exploration — requires multi-phase test harness.

---

### TEST-9. `docs/memory.md` low signal-to-noise — LOW [1/4]

**Reported by:** Claude (4A)

179 lines of accumulated observations. Most entries are generic. Genuinely
useful project-specific entries are buried.

**Action:** Directly fixable — prune to ~30 high-value entries.

---

## 7. Security Considerations [1/4]

**Reported by:** Kiro only

| Issue | Risk | Action |
|-------|------|--------|
| No input sanitization on spec content before LLM prompts | Medium | Needs exploration |
| No API rate limiting / 429 backoff | Medium | Needs exploration |
| State files (JSONL) not checksummed | Low | Needs exploration |
| No dependency depth limit in graph resolution | Low | Needs exploration |

---

## Summary: Directly Fixable Items

These can be fixed now without design decisions or new specs:

| # | Item | Severity | Effort |
|---|------|----------|--------|
| 1 | BUG-1: Wire fox tools through ClaudeBackend | High | Medium |
| 2 | BUG-2: Fix branch name in `reset.py` | High | Small |
| 3 | BUG-3: Fix JSON error envelope message | Medium | Small |
| 4 | BUG-4: Fix return type annotation in `fix.py` | Medium | Small |
| 5 | BUG-5: Await `run_fix_loop` coroutine | Medium | Small |
| 6 | BUG-6: Fix banner test fixture | Low | Small |
| 7 | SMELL-1: Extract `spec/ai_validator.py` | High | Medium |
| 8 | SMELL-7: Consolidate metric tracking | Medium | Small |
| 9 | SMELL-8: Single source for tool schemas | Low | Medium |
| 10 | SMELL-9: Rename `NodeTiming.float` | Medium | Small |
| 11 | SMELL-10: Create `core/paths.py` | Medium | Medium |
| 12 | SMELL-11: Broaden `github_issues.py` catch | Medium | Small |
| 13 | SMELL-12: `TYPE_CHECKING` guard for duckdb | Low | Small |
| 14 | SMELL-13: Fix `BaseException` catch in fox_edit | Low | Small |
| 15 | SMELL-14: Complete `_ROLE_TO_ARCHETYPE` | Low | Small |
| 16 | SMELL-15: Remove redundant exception catch | Low | Small |
| 17 | DEAD-2: Implement or remove `plan --verify` | Medium | Small |
| 18 | DEAD-4: Add `GraphSync.predecessors()` | Low | Small |
| 19 | DEAD-5: Remove unused `first_dispatch` param | Low | Small |
| 20 | DEAD-6: Remove unused `archetypes.backends` | Low | Small |
| 21 | LINT-1: Fix ruff errors | Low | Small |
| 22 | SPEC-4: Update embedding model spec | Low | Small |
| 23 | TEST-2: Add `session_lifecycle.py` unit tests | High | Medium |
| 24 | TEST-3: Add `reset.py` unit tests | High | Medium |
| 25 | TEST-4: Replace placeholder backend tests | Medium | Medium |
| 26 | TEST-7: Add knowledge store failure tests | Medium | Medium |
| 27 | TEST-9: Prune `docs/memory.md` | Low | Small |

## Summary: Items Needing Exploration

These require design decisions, new specs, or further investigation:

| # | Item | Severity | Blocker |
|---|------|----------|---------|
| 1 | DEAD-1: Wire archetype pipeline end-to-end | Critical | Needs corrective spec |
| 2 | SMELL-2: Harvest race condition | High | Needs design decision (serialize vs worktree) |
| 3 | DEAD-3: Unwired CLI commands governance | Medium | Needs formal spec supersession |
| 4 | SMELL-3: Config simplification | Medium | Needs design proposal |
| 5 | SMELL-4: Orchestrator decomposition | Medium | Needs design proposal |
| 6 | SMELL-5: Memory system consolidation | Medium | Needs design decision |
| 7 | SMELL-6: Silent failure visibility | Medium | Needs design decision |
| 8 | SMELL-16: Custom tool permission policy | Medium | Needs policy decision |
| 9 | SMELL-17: `lint-spec --fix` side effects | Medium | Needs policy decision |
| 10 | SPEC-3: Spec/errata governance | Medium | Needs process decision |
| 11 | TEST-1: Archetype integration test | High | Blocked by DEAD-1 |
| 12 | TEST-6: Parallel harvest test | Medium | Blocked by SMELL-2 |
| 13 | TEST-5: CLI integration tests | Medium | Needs test infrastructure |
| 14 | TEST-8: Hot-loading integration test | Medium | Needs test harness |

---

## 8. Feature Suggestions

These are new feature ideas from the auditors, not bugs or debt. Listed by
how many auditors independently proposed similar concepts.

### Proposed by multiple auditors

| Idea | Auditors | Description |
|------|----------|-------------|
| **Session replay / debug mode** | Claude (5D), Cursor (Idea 3) | `agent-fox replay <node_id>` to re-assemble and display exact prompts/actions without executing. `agent-fox why <file>` to trace which sessions touched a file. |
| **Adaptive / differential context** | Claude (5C), Codex (#3) | Compute minimal, intent-aware context bundles per task. Only include what changed since last session. Dramatically reduce token usage on retries. |
| **Adaptive model selection** | Cursor (Idea 4), Kiro (#2) | Analyze task complexity and select model tier automatically. Track cost/quality to learn optimal model per task type. |

### Proposed by single auditor

| Idea | Auditor | Description |
|------|---------|-------------|
| **Fox Watch — continuous autonomous dev** | Cursor | Monitor `.specs/` for changes, auto re-plan and execute. "Push a spec, get code." |
| **Self-healing via spec mutation** | Cursor | On repeated failures, generate modified specs that work around blockers. |
| **Plugin-based lint rule system** | Cursor | Each rule is a module with `check()`, auto-discovered from `spec/rules/`. |
| **Spec-as-executable contracts** | Codex | Generate coverage contracts from spec requirement IDs; fail CI on unmapped requirements. |
| **Capability graph runtime** | Codex | Replace hardcoded backend/tool wiring with declarative capability graph. |
| **Fox tools as default** | Claude | Make `tools.fox_tools = true` the default for all users. |
| **Agent collaboration mode** | Kiro | Run Skeptic/Coder/Verifier concurrently with message passing instead of sequentially. |
| **Spec generation from codebase** | Kiro | Reverse-engineer specs from existing code to lower adoption barrier. |
| **Visual plan editor** | Kiro | Web UI for visualizing and editing task graphs interactively. |
| **Agent specialization marketplace** | Kiro | Community-contributed archetypes, tools, hooks installable via CLI. |
| **Dry-run mode** | Kiro | `agent-fox code --dry-run` to preview task order, estimated cost, validation. |
| **Snapshot / rollback** | Kiro | `agent-fox snapshot create/rollback` for easy recovery from bad agent decisions. |

---

## Auditor Agreement Matrix

Shows which auditors identified each major finding category:

| Finding | Cursor | Codex | Claude | Kiro |
|---------|--------|-------|--------|------|
| Fox tools not wired to backend | x | x | ~ | |
| Archetype pipeline unwired | | | x | x |
| `reset.py` branch name bug | x | | | |
| JSON error envelope bug | | x | | |
| `spec/validator.py` too large | x | x | | |
| Harvest race condition | | | x | x |
| Config sprawl | | | x | x |
| Orchestrator god object | | | | x |
| Dual memory systems | | | | x |
| Silent failures | | | | x |
| No archetype integration test | x | | x | x |
| Backend tests are placeholder | | x | x | |
| Session lifecycle untested | x | | x | |
| Security concerns | | x | | x |

`x` = explicitly reported, `~` = implied but not called out as primary finding
