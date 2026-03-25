# PRD: Sync Barrier Hardening

## Problem Statement

The current sync barrier implementation has several reliability gaps:

1. **No parallel drain.** In parallel dispatch mode, the barrier fires inline
   after a single task completes while other tasks are still in-flight. The
   barrier's contract — "no agent should be running" — is violated.

2. **No worktree verification.** Each session merges its feature branch into
   develop via `harvest()`, but there is no verification step at the barrier to
   confirm that all worktrees have been cleaned up and all changes are on
   develop.

3. **Unidirectional develop sync.** `ensure_develop()` pulls remote changes
   into local develop, but never pushes local develop to origin. After the
   barrier merges several sessions' work, origin/develop drifts behind.

4. **Untracked specs can be hot-loaded.** `discover_new_specs()` scans the
   filesystem, so a spec folder that exists on disk but is not committed to
   develop can be incorporated into the plan — leading to planning errors when
   the folder disappears on the next worktree checkout.

5. **Incomplete specs can be hot-loaded.** A spec folder with only a `prd.md`
   and `tasks.md` (missing `requirements.md`, `design.md`, `test_spec.md`)
   can be added to the plan, producing nodes that will fail immediately.

6. **Broken specs can be hot-loaded.** A spec that has all five files but
   contains structural errors (broken dependency references, missing acceptance
   criteria, etc.) is accepted without validation.

## Proposed Solution

Harden the sync barrier entry sequence and spec hot-load gate:

### Barrier Entry (before any hot-load or knowledge work)

1. **Drain parallel pool.** If parallel dispatch is active, wait for all
   in-flight tasks to complete and process their results before entering the
   barrier. This ensures no agents are running during the barrier.

2. **Verify worktrees.** Scan `.agent-fox/worktrees/` for any remaining
   directories. If found, log a warning with the paths — these are orphaned
   worktrees whose changes may not be on develop.

3. **Bidirectional develop sync.** Pull remote changes into local develop
   (fetch + fast-forward/rebase via existing `_sync_develop_with_remote`), then
   push local develop to origin. Use the existing `MergeLock` for
   serialization.

### Hot-Load Gate (spec acceptance criteria)

A new spec discovered in `.specs/` is only incorporated into the plan if **all
three** of the following gates pass:

4. **Git-tracked on develop.** The spec folder must be committed to the local
   `develop` branch (checked via `git ls-tree`). Untracked or uncommitted
   folders are skipped.

5. **Complete.** All five required documents must exist: `prd.md`,
   `requirements.md`, `design.md`, `test_spec.md`, `tasks.md`.

6. **Lint-clean.** Running the spec validator produces no findings with
   severity `error`. Warnings and hints are acceptable.

### Skip & Re-evaluate

Specs that fail any gate are silently skipped (with a log message) and
re-evaluated at the next sync barrier with a clean slate — no memory of prior
failure is kept.

## Clarifications

- **Q1:** "Merge all worktree changes" means a *verification* step — confirm no
  outstanding worktrees remain unmerged — not an explicit merge-all operation.
  Each session already merges via `harvest()`.
- **Q2:** Develop sync is *bidirectional*: pull then push.
- **Q3:** "Committed to develop" means `git ls-tree develop -- .specs/NN_name`
  returns entries — the folder is tracked, not just present on disk.
- **Q4:** "Blocking errors" means findings with severity `error` only.
  Warnings and hints do not block.
- **Q5:** Skipped specs are re-evaluated at the next barrier with no memory of
  prior failure (clean slate).
- **Q6:** In parallel mode, the barrier waits for all in-flight tasks to finish
  before entering the sync state.

## Dependencies

No cross-spec dependencies. The upstream specs (06\_hooks\_sync\_security,
45\_robust\_merge) are fully implemented and archived — their code is already
on `develop`. This spec builds on that existing infrastructure without
requiring any spec-level dependency edges.

## Scope

- This spec modifies `engine/engine.py`, `engine/hot_load.py`, and
  `workspace/develop.py` (or a new barrier module).
- It does **not** change the session lifecycle, harvest logic, or worktree
  creation/destruction — those are upstream of the barrier.
- It does **not** add new CLI commands or configuration keys.
