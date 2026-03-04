# Agent-Fox v2 — Merged Get-Well Plan

| Field     | Value          |
|-----------|----------------|
| Date      | 2026-03-04     |
| Branch    | develop        |
| Baseline  | 933 tests pass, 0 lint errors, 87 files need ruff format, 233 warnings |
| Sources   | 4 independent audits (Codex, Cursor/Claude Code, Kiro, spec-audit tool) |

---

## Executive Summary

Four independent audits converge on the same picture: the codebase is ~85%
spec-complete with solid architecture, 933 passing tests, and well-structured
modules. The remaining 15% is a combination of **missing code** (unimplemented
specs, disconnected plumbing), **hygiene issues** (deprecation warnings,
formatting, duplicate types), and **structural debt** (misplaced code, over-
abstraction). All four audits agree on the top items — the plan below merges
and de-duplicates their findings into a single prioritized roadmap.

**Principle: implement missing code before refactoring existing code.**

---

## Phase 1: Missing Code — High Priority

These are functional gaps where the specs require behavior the code doesn't
deliver. Every audit flagged these.

### 1.1 Spec 17 — Init Claude Settings (ALL 4 AUDITS)

**Requirement IDs:** 17-REQ-1.1 through 17-REQ-2.E3 (10 requirements, 0% complete)

**What:** `agent-fox init` should create/update `.claude/settings.local.json`
with a `CANONICAL_PERMISSIONS` list so Claude Code sessions don't trigger
interactive permission prompts. On re-init, merge (not overwrite) existing
settings.

**Why:** Without this, every coding session opens with permission dialogs,
breaking the "unattended overnight" promise.

**Implementation:**
- Add `CANONICAL_PERMISSIONS` constant to `agent_fox/cli/init.py`
- Add `_ensure_claude_settings(project_root: Path)` helper
- Wire into both init paths (fresh + already-initialized)
- Handle edge cases: invalid JSON, missing `permissions.allow`, idempotency
- Tests: `tests/unit/cli/test_claude_settings.py`

**Estimated scope:** ~120 lines + tests

### 1.2 Fix Loop — Wire Session Execution (3/4 AUDITS: Cursor, Codex audit-report)

**Requirement IDs:** 08-REQ-5.1, 08-REQ-5.2, 08-REQ-5.3

**What:** `fix/loop.py` generates fix specs but **never runs coding sessions**.
The comment at lines 118-121 says "Session runner integration is handled at the
CLI level" — but it isn't. `agent-fox fix` is a spec generator, not an auto-fixer.

**Why:** This is the single largest functional gap. The fix command is half-built.

**Implementation:**
- Accept a `session_runner` callable in `run_fix_loop()`
- Invoke sessions for each generated fix spec
- Track cost from session outcomes; terminate on limit
- Wire in `cli/fix.py` with the same factory pattern as `cli/code.py`
- Add `--dry-run` flag (generate specs only, no sessions)

**Estimated scope:** ~80 lines changed across `fix/loop.py`, `cli/fix.py`

### 1.3 Time Vision — Temporal Queries + Timeline (3/4 AUDITS: Cursor, audit-report, Kiro)

**Requirement IDs:** 13-REQ-4.1, 13-REQ-4.2, 13-REQ-6.1, 13-REQ-6.2, 13-REQ-6.3

**What:** The temporal query subsystem is entirely missing. The causal graph
infrastructure exists (`knowledge/causal.py`) but there's no way to query it
or render timelines.

**Why:** 5 HIGH-priority audit items. Core deliverable of spec 13.

**Implementation:**
- Create `knowledge/temporal.py`: `temporal_query()` combining vector search +
  causal traversal; `TimelineNode` and `Timeline` dataclasses
- Create `knowledge/timeline_renderer.py`: `render_timeline()` with indented
  text, provenance, and TTY-aware color
- Wire into `ask` command for temporal queries
- Wire into `patterns` command for causal cross-reference

**Estimated scope:** ~230 lines across 2 new files + wiring

### 1.4 Allowlist Hook — Wire into Session Runner (3/4 AUDITS: Cursor, audit-report, GET_WELL_PLAN)

**Requirement IDs:** 03-REQ-3.4, 03-REQ-8.1

**What:** The command allowlist hook exists in two places but is wired into
**neither** the session execution path. `run_session()` creates
`ClaudeCodeOptions` without passing the hook. Security gap.

**Why:** Security-relevant. The allowlist exists but doesn't enforce anything.

**Implementation:**
- Delete duplicate `DEFAULT_BASH_ALLOWLIST` + `build_allowlist_hook()` from
  `session/runner.py` (~120 lines removed)
- Keep `hooks/security.py` as the single source of truth (better implementation:
  path stripping, frozenset, configurable)
- Wire `make_pre_tool_use_hook()` into `run_session()` via `ClaudeCodeOptions`

**Estimated scope:** ~120 lines removed, ~15 lines added. Net reduction.

### 1.5 Data Model Foundation (2/4 AUDITS: Cursor, GET_WELL_PLAN)

**What:** `Fact` dataclass is missing `session_id` and `commit_sha` fields.
`SessionRecord` lacks a `model` field. `SessionOutcome.files_touched` is never
populated. These gaps cascade into 6 downstream failures:

- 12-REQ-1.3: Fact provenance always NULL
- 13-REQ-1.1: Provenance unavailable during extraction
- 07-REQ-2.3: File overlap detection disabled (empty `files_touched`)
- 07-REQ-2.5: Cost breakdown lumps everything into "default" tier

**Implementation:**
- Add `session_id: str | None = None` and `commit_sha: str | None = None` to
  `memory/types.py:Fact`
- Add `model: str = ""` to `engine/state.py:SessionRecord`
- Populate `session_id` in `extract_facts()`
- Populate `commit_sha` after harvest
- Populate `files_touched` after harvest via `git diff --name-only`
- Populate `model` in `SessionRecord` from resolved model name

**Estimated scope:** ~50 lines across 5 files. Low risk (additive defaults).

### 1.6 Pattern Detection — Causal Validation (2/4 AUDITS: GET_WELL_PLAN, Cursor)

**Requirement ID:** 13-REQ-5.1 (partial)

**What:** `knowledge/patterns.py:detect_patterns()` finds co-occurrences but
never validates against the causal graph. Patterns are correlations, not
causations.

**Implementation:**
- Add JOIN against `fact_causes` in detection SQL
- Filter to patterns with actual causal links

**Estimated scope:** ~20 lines

### 1.7 Git Commit Ingestion — Include Body (2/4 AUDITS: GET_WELL_PLAN, Cursor)

**What:** `knowledge/ingest.py:ingest_git_commits()` only captures the commit
subject. The spec says "subject + body" for searchable commit context.

**Implementation:**
- Change git log format from `%s` to `%s%n%n%b`, update parsing

**Estimated scope:** ~15 lines

---

## Phase 2: Hygiene & Correctness

These are bugs, warnings, and inconsistencies. Quick fixes with high signal.

### 2.1 Fix datetime.utcnow() Deprecation (ALL 4 AUDITS)

**What:** 233 warnings from `datetime.utcnow()` deprecated in Python 3.12+.

**Fix:** Global replace `datetime.utcnow()` with `datetime.now(UTC)`, add
`from datetime import UTC` imports.

**Estimated scope:** ~10 lines across 3-5 files

### 2.2 Ruff Format (3/4 AUDITS)

**What:** 87 files need `ruff format`.

**Fix:** `ruff format .`

**Estimated scope:** One command

### 2.3 DuckDB Insert Duplicate Handling (2/4 AUDITS: GET_WELL_PLAN, Cursor)

**What:** `memory/store.py:_write_to_duckdb()` does raw INSERT. Duplicate
fact IDs cause silent failures — facts end up in JSONL but not DuckDB.

**Fix:** Use `INSERT OR IGNORE` or pre-check for existing IDs.

**Estimated scope:** ~5 lines

### 2.4 Hot-Load Persistence Gap (2/4 AUDITS: GET_WELL_PLAN, Cursor)

**What:** Hot-loaded specs aren't persisted to `plan.json` until orchestrator
shutdown. A crash after hot-load loses newly discovered specs.

**Fix:** Call `_sync_plan_statuses()` immediately after hot-load succeeds.

**Estimated scope:** ~10 lines in orchestrator.py

### 2.5 Causal Link Referential Integrity (2/4 AUDITS: Cursor, audit-report)

**Requirement ID:** 13-REQ-2.E2

**What:** `store_causal_links()` uses `INSERT OR IGNORE` without checking that
both fact IDs exist. No warning logged for dangling references.

**Fix:** Pre-check existence, skip and log warning for missing IDs.

**Estimated scope:** ~10 lines in `knowledge/causal.py`

---

## Phase 3: Structural Simplification

Refactors that reduce complexity without changing behavior. Only after Phases
1-2 are complete.

### 3.1 Unify SessionOutcome Types (3/4 AUDITS)

**What:** Two `SessionOutcome` dataclasses exist:
- `session/runner.py:SessionOutcome` — returned by session runner
- `knowledge/sink.py:SessionOutcome` — consumed by sink dispatcher

`cli/code.py` manually maps between them with aliasing. Unnecessary indirection.

**Fix:** Make `sink.SessionOutcome` the single type. Delete the runner's copy.

**Estimated scope:** ~40 lines across 3 files

### 3.2 Extract SessionLifecycle from cli/code.py (ALL 4 AUDITS)

**What:** `cli/code.py` is 759 lines. `_NodeSessionRunner` (~480 lines) handles
the full session lifecycle (worktree, hooks, context, execution, harvesting,
knowledge extraction, sink recording). This is a domain class masquerading as
a CLI helper.

**Fix:**
- Move `_NodeSessionRunner` to `engine/session_lifecycle.py`
- `cli/code.py` becomes a thin wrapper (~200 lines)
- Move causal extraction LLM call to `memory/extraction.py`

**Estimated scope:** ~600 lines moved, ~80 lines of wiring. Depends on 3.1.

### 3.3 Minor Cleanup Batch

Small items, independently completable:

| Item | File | Lines | Description |
|------|------|-------|-------------|
| 3.3a | engine/reset.py | ~20 | Extract `_cleanup_workspace()` helper (duplicated in `reset_all` and `reset_task`) |
| 3.3b | engine/parallel.py | ~15 | Extract `_failure_record()` helper (duplicated in `execute_one` and `execute_batch`) |
| 3.3c | memory/store.py | ~5 | Remove `_write_to_jsonl` wrapper (just calls `append_facts()`) |
| 3.3d | workspace/harvester.py | ~2 | Use `rebase_onto()` instead of raw `run_git(["rebase", ...])` |

---

## Execution Order

Priority-ordered. Missing code first, then hygiene, then structure.

| # | Item | Phase | Risk | Est. | Depends On |
|---|------|-------|------|------|------------|
| 1 | 2.2 Ruff format | P2 | None | 1 min | -- |
| 2 | 2.1 Fix datetime.utcnow() | P2 | Low | 15 min | -- |
| 3 | 2.3 DuckDB duplicate handling | P2 | Low | 15 min | -- |
| 4 | 2.5 Causal link integrity | P2 | Low | 15 min | -- |
| 5 | 1.5 Data model foundation | P1 | Low | 1 hr | -- |
| 6 | 1.1 Spec 17: Init Claude Settings | P1 | Low | 2 hrs | -- |
| 7 | 1.4 Wire allowlist hook | P1 | Med | 1 hr | -- |
| 8 | 1.6 Pattern detection causal join | P1 | Low | 30 min | -- |
| 9 | 1.7 Git commit body ingestion | P1 | Low | 15 min | -- |
| 10 | 1.2 Wire fix loop sessions | P1 | Med-Hi | 2 hrs | -- |
| 11 | 1.3 Time Vision temporal queries | P1 | Med | 3 hrs | -- |
| 12 | 2.4 Hot-load persistence | P2 | Med | 30 min | -- |
| 13 | 3.1 Unify SessionOutcome | P3 | Med | 1 hr | -- |
| 14 | 3.2 Extract SessionLifecycle | P3 | Med | 3 hrs | #13 |
| 15 | 3.3a-d Minor cleanup | P3 | Low | 30 min | -- |

Items 1-4 form a hygiene batch (one session).
Items 5-9 are independent feature sessions.
Items 10-11 are larger feature work.
Item 14 depends on item 13.

---

## What's Intentionally Left Alone

All four audits agree these are NOT problems:

- **Test suite** — 933 passing tests, good coverage. Not touching tests for
  DRY or style.
- **Core engine** — orchestrator.py is large (754 lines) but cohesive and
  well-tested. Its complexity is earned.
- **Knowledge module** — 11 files, zero duplication, distinct responsibilities.
- **Hook system** — Fully implemented, well-tested, clean separation.
- **Platform integration** — Clean protocol/factory pattern, both
  implementations complete.
- **Fix pipeline** — 6 files with clear pipeline structure (the gap is wiring,
  not architecture).
- **Spec files** — Already batch-updated in commit 8ea0c7f.

---

## Success Criteria

The codebase is "well" when:

1. All 933+ existing tests still pass
2. Zero deprecation warnings (datetime.utcnow eliminated)
3. `make lint` and `ruff format --check .` pass clean
4. Spec 17 (Init Claude Settings) is implemented with tests
5. `agent-fox fix` runs actual coding sessions (not just spec generation)
6. Temporal queries and timeline rendering work via `agent-fox ask`
7. Allowlist hook is wired and enforcing in session execution
8. `Fact` has session_id and commit_sha; `SessionOutcome.files_touched` populated
9. Pattern detection validates against causal graph
10. `cli/code.py` is under 250 lines (lifecycle extracted)
11. Single `SessionOutcome` type (no aliasing)
12. No silent DuckDB insert failures on duplicate facts

---

## Cross-Audit Agreement Matrix

Items are listed by how many independent audits flagged them.

| Item | Codex | Cursor | Kiro | GET_WELL | audit-report |
|------|-------|--------|------|----------|--------------|
| Spec 17 missing | x | x | x | x | x |
| Extract SessionLifecycle | x | x | x | x | |
| datetime.utcnow() | x | x | x | x | |
| Fix loop not wired | | x | | | x |
| Time Vision missing | | x | | | x |
| Allowlist not wired | | x | | x | x |
| Duplicate SessionOutcome | | x | | x | |
| Ruff format | x | | x | x | |
| Data model gaps | | x | | x | |
| Pattern causal validation | | x | | x | |
| DuckDB duplicate handling | | | | x | |
| Hot-load persistence | | | | x | |
