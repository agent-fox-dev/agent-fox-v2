# Agent-Fox v2 — Code Audit Report

**Date:** 2026-03-10
**Auditor:** Cursor (Claude)
**Branch:** `develop`
**Baseline:** 1545 tests passed, 3 failed; ruff reports 13 errors

---

## 1. Bugs

### B1. `reset.py` branch name format mismatch — HIGH

`_task_id_to_branch_name` (line 98) produces `feature/{spec}-{group}` (hyphen),
but `workspace.py:create_worktree` (line 491) uses `feature/{spec}/{group}`
(slash). The reset command will **never delete the correct feature branch**.
Branch cleanup is silently ineffective.

**File:** `agent_fox/engine/reset.py:98`
**Fix:** Change `f"feature/{parts[0]}-{parts[1]}"` to
`f"feature/{parts[0]}/{parts[1]}"`.

### B2. Fox tools never reach the Claude backend — HIGH

`session.py` builds fox tool definitions and passes them via
`backend.execute(..., tools=fox_tools)`. `ClaudeBackend.execute` accepts
`tools` in its signature but **never forwards them** to `ClaudeCodeOptions`.
The entire spec 29 fox-tools-in-session feature is non-functional in
production. The MCP server path works correctly; only the in-process
session path is broken.

**File:** `agent_fox/session/backends/claude.py:97–103`
**Fix:** Forward the `tools` parameter to `ClaudeCodeOptions` (requires
verifying how `claude-code-sdk` accepts custom tool definitions).

### B3. `_build_fix_session_runner` wrong return type — MEDIUM

Annotated as `-> TerminationReason | None` but actually returns an async
callable (`_run`). The `# type: ignore[return-value]` on line 63 hides the
real type error.

**File:** `agent_fox/cli/fix.py:31–63`
**Fix:** Change the return annotation to match the actual return type (the
inner async callable type, or a dedicated `FixSessionRunner` type alias).

### B4. 3 banner styling tests fail — LOW

Tests expect ANSI escape codes in banner output but `Console` is not emitting
them in the test environment. Likely a `force_terminal=True` or `color_system`
configuration issue in the test fixture.

**Files:** `tests/unit/ui/test_banner.py` (lines 173, 188, 200)

---

## 2. Lint / Hygiene Issues

### L1. ruff reports 13 errors

| File | Rule | Count | Description |
|------|------|-------|-------------|
| `cli/plan.py` | I001 | 1 | Unsorted import block |
| `fix/__init__.py` | I001 | 1 | Unsorted import block |
| `reporting/standup.py` | E501 | 1 | Line too long (92 > 88) |
| `spec/validator.py` | E402 | 8 | Module-level imports not at top of file |
| `spec/validator.py` | F811 | 2 | Redefined imports (`_DEP_TABLE_HEADER_ALT`, `_parse_table_rows`) |

The `spec/validator.py` E402/F811 cluster stems from a second import block
at line 1634 — the AI validation section was appended as a separate
"mini-module" inside the same file, with aliased imports to avoid name
clashes.

---

## 3. Holes — Unwired / Dead Code

### H1. `plan --verify` prints "not yet implemented" — MEDIUM

The `--verify` flag exists in the CLI but does nothing
(`cli/plan.py:197–199`). Either implement or remove.

### H2. `ask`, `patterns`, `compact` CLI commands are unwired — MEDIUM

Documented intentionally in `docs/errata/unwired_cli_commands.md`. The
backing modules (`Oracle.ask()`, `detect_patterns()`, `render_patterns()`,
`compact()`) are maintained and tested without any production entry point.
This creates ongoing maintenance burden for dead code.

### H3. `Orchestrator._get_predecessors` uses private `GraphSync._edges` — LOW

Accesses a private attribute instead of a public API. A
`GraphSync.predecessors(node_id)` method should be added.

### H4. `first_dispatch` unused in parallel mode — LOW

The parameter is passed to `_dispatch_parallel` but never referenced there.

### H5. Redundant exception catch in `integration.py` — LOW

`(IntegrationError, Exception)` — `IntegrationError` is already a subclass
of `Exception`.

---

## 4. Code Smell

### S1. `spec/validator.py` is 1700+ lines with two import sections — HIGH

The AI validation logic was appended at line 1634 with its own imports,
aliased to avoid name collisions (`_logging_ai`, `_re_ai`,
`_defaultdict_ai`). This should be extracted into a separate
`spec/ai_validator.py` module.

### S2. `NodeTiming.float` shadows the Python builtin — MEDIUM

`graph/resolver.py:192` defines a field `float: int`. Should be renamed to
`slack` or `total_float`.

### S3. Hardcoded paths scattered across CLI commands — MEDIUM

`.agent-fox`, `.specs`, `plan.json`, `state.jsonl`, `worktrees/`,
`config.toml` are each hardcoded in multiple CLI files. A single constants
module (e.g. `core/paths.py`) would reduce duplication and enable future
configurability.

### S4. `github_issues.py` exception handling too narrow — MEDIUM

Docstring says failures should never propagate, but only
`IntegrationError` is caught. Other exceptions (`httpx.HTTPError`,
`KeyError`, etc.) would escape.

### S5. Duplicate tool schemas between registry and MCP server — LOW

Tool definitions in `tools/registry.py` and `tools/server.py` define the
same schemas independently. Changes to one must be manually mirrored in the
other.

---

## 5. Test Coverage Gaps

### Well-tested (good coverage)

- Tools (read, edit, search, outline, hashing, registry, MCP server)
- Spec parsing, validation, fixing
- Graph (builder, analyzer, fast mode, resolver)
- Session (prompt, convergence, review parser, archetypes, backends)
- Knowledge (DuckDB, review store, ingest, temporal, patterns, dual write)
- Engine (orchestrator core, serial/parallel, sync, circuit breaker)
- UI (progress, events, banner)

### Untested modules

| Module | Risk |
|--------|------|
| `engine/reset.py` | High — contains the branch name bug (B1) |
| `engine/session_lifecycle.py` | High — core lifecycle orchestration |
| `workspace/integration.py` | Medium — post-harvest push/PR |
| `engine/hot_load.py` | Medium — sync-barrier feature |
| `engine/knowledge_harvest.py` | Medium |
| `knowledge/embeddings.py` | Medium |
| `knowledge/query.py` (Oracle) | Medium |
| `knowledge/search.py` | Medium |
| `knowledge/sink.py`, `jsonl_sink.py`, `duckdb_sink.py` | Medium |
| `memory/memory.py`, `memory/filter.py` | Low |
| `hooks/security.py` | Low |
| `core/client.py`, `core/models.py` | Low |

### Missing integration tests

| Command | Status |
|---------|--------|
| `agent-fox code` | No integration test (the primary command) |
| `agent-fox fix` | No integration test |
| `agent-fox status` | No integration test |
| `agent-fox standup` | No integration test |
| `agent-fox reset` | No integration test |

---

## 6. Spec Compliance

All 30 specs (01–29 plus fix specs) report tasks as completed. Two
compliance gaps:

1. **Spec 29 (fox tools in sessions):** Non-functional due to B2. The MCP
   server path works; only the in-process session path is broken.
2. **Spec 02 (`--verify`):** Flagged as placeholder (H1). The requirement
   02-REQ-7.5 is unimplemented.

---

## 7. Get-Well Plan

### Phase 1: Critical Bugs

| # | Item | Ref | Effort |
|---|------|-----|--------|
| 1 | Fix branch name format in `reset.py` | B1 | Small |
| 2 | Wire fox tools through `ClaudeBackend` | B2 | Medium |
| 3 | Fix `_build_fix_session_runner` return type | B3 | Small |
| 4 | Fix 3 banner styling tests | B4 | Small |

### Phase 2: Lint & Hygiene

| # | Item | Ref | Effort |
|---|------|-----|--------|
| 5 | Run `ruff check --fix` and manually fix remainder | L1 | Small |
| 6 | Extract AI validation into `spec/ai_validator.py` | S1 | Medium |

### Phase 3: Code Quality

| # | Item | Ref | Effort |
|---|------|-----|--------|
| 7 | Rename `NodeTiming.float` to `slack` | S2 | Small |
| 8 | Create `core/paths.py` for path constants | S3 | Medium |
| 9 | Broaden exception handling in `github_issues.py` | S4 | Small |
| 10 | Add `GraphSync.predecessors()` public API | H3 | Small |
| 11 | Consolidate tool schemas (single source of truth) | S5 | Medium |
| 12 | Implement or remove `plan --verify` | H1 | Small |
| 13 | Remove dead `first_dispatch` param; simplify catch | H4, H5 | Small |

### Phase 4: Test Coverage

| # | Item | Ref | Effort |
|---|------|-----|--------|
| 14 | Add unit tests for `engine/reset.py` | B1 | Medium |
| 15 | Add unit tests for `engine/session_lifecycle.py` | — | Medium |
| 16 | Add integration test for `agent-fox code` (smoke) | — | Medium |
| 17 | Add tests for `workspace/integration.py` | — | Medium |
| 18 | Add tests for `hot_load.py`, `knowledge_harvest.py` | — | Medium |

---

## 8. Ideas — Radical Improvements

### Idea 1: "Fox Watch" — Continuous autonomous development

Instead of `agent-fox code` being a one-shot batch, add `agent-fox watch`:

- Monitor `.specs/` for new or changed specs
- Automatically re-plan and execute new tasks
- Integrate with `git push` webhooks to trigger on remote spec changes
- Turns agent-fox into a **continuous integration agent** — push a spec,
  get code

No other orchestrator does "push a spec, get code."

### Idea 2: Plugin-based lint rule system

`spec/validator.py` is 1700+ lines mixing structural validation, AI
validation, dependency checking, and fixers. Refactor into:

- Each rule is a separate module with a `check()` function
- Rules auto-discovered from a `spec/rules/` directory
- AI-powered rules are just rules with an async `check()` variant
- Trivial to add new rules; massively reduces cognitive load

### Idea 3: Session replay and debugging

Store full session transcripts and add:

- `agent-fox replay <task-id>` — show what the agent did, tool by tool
- `agent-fox diff <task-id>` — show just the code changes per session
- `agent-fox why <file>` — trace which sessions touched a file and why

Makes agent-fox debuggable in ways no competitor offers.

### Idea 4: Adaptive model selection

Analyze task complexity and automatically select model tier:

- Fast/cheap model for boilerplate (config, docs, simple tests)
- Powerful model for complex tasks (architecture, multi-file)
- Track cost-per-task and quality metrics to learn optimal model per
  task type over time

### Idea 5: Self-healing via spec mutation

When a session fails repeatedly, instead of retrying the same spec:

- Analyze the failure pattern
- Generate a modified spec that works around the blocker
- Run the modified spec
- If successful, flag the original spec for human review

Turns retries from "try the same thing again" into "try a different
approach."
