# PRD: DB-Based Plan State

## Problem

agent-fox tracks plan structure and execution state across three file-based
stores — `plan.json`, `state.jsonl`, and `tasks.md` checkboxes. This
architecture has five concrete problems:

1. **No transactional consistency.** Node status is saved to `state.jsonl`
   first, then `plan.json` is updated later. A crash between saves leaves
   state ahead of plan or vice versa. There is no atomic operation that
   updates both together.

2. **Duplication.** `session_outcomes` (DuckDB) and `SessionRecord`
   (`state.jsonl`) both record session results with different field sets.
   The same session produces two records in two systems that cannot be
   joined without manual reconciliation.

3. **Unbounded growth.** `state.jsonl` appends a full state snapshot (every
   node status, every session record, every cost counter) on each save.
   A multi-spec run produces a multi-megabyte file of mostly-redundant
   snapshots.

4. **No concurrent access safety.** No lock file protects `.agent-fox/`.
   `af status` reading `state.jsonl` while the orchestrator appends to it
   can read partial lines. Multiple orchestrators writing to the same files
   produce corruption.

5. **Checkbox fragility.** `plan.json` stores a copy of `tasks.md` body
   with checkboxes that are never updated after plan creation. The v3
   architecture doc already identifies this: "checkbox state in markdown
   is a presentation concern, not a reliable state machine."

## Solution

Move all plan structure and execution state from file-based stores into
DuckDB — the same database that already holds `session_outcomes`,
`audit_events`, and knowledge facts.

Specifically:

1. **New `plan_nodes` table** — stores the plan DAG nodes with their
   statuses, replacing `plan.json` nodes and `state.jsonl` node_states.

2. **New `plan_edges` table** — stores dependency edges, replacing
   `plan.json` edges.

3. **New `plan_meta` table** — stores plan-level metadata (content hash,
   creation timestamp, version), replacing `plan.json` metadata.

4. **New `runs` table** — stores per-run aggregates (total tokens, cost,
   sessions, status), replacing `state.jsonl` run-level fields.

5. **Extended `session_outcomes`** — add the missing `SessionRecord` fields
   (cost, model, archetype, commit_sha, error_message, attempt,
   is_transport_error, run_id), eliminating the duplication.

6. **Drop `plan.json` and `state.jsonl`** — remove all code that reads or
   writes these files. Remove their path constants. Remove their `.gitignore`
   exceptions if any.

The in-memory `GraphSync` pattern (shared `node_states` dict) remains
unchanged — the dict is loaded from DB on startup and persisted to DB after
each status change. This is a persistence-layer swap, not an algorithm change.

## Clarifications

1. **Session outcomes strategy:** Extend the existing `session_outcomes` table
   with the missing columns from `SessionRecord`. Do not create a separate
   `sessions` table.

2. **plan.json disposition:** Drop entirely. No file on disk. `af plan`
   renders a human-readable view from the database.

3. **Git tracking:** Not applicable — `plan.json` and `state.jsonl` are
   removed entirely, so there is nothing to track.

4. **Migration path:** Clean break. Existing `plan.json` and `state.jsonl`
   files are ignored. No data import from old files.

5. **Concurrent access:** `af status` must be able to read plan state while
   the orchestrator is running. DuckDB supports concurrent readers with a
   single writer.

6. **DuckDB as hard dependency:** Yes. DuckDB is required for all state
   operations (`af run`, `af plan`, `af status`, `af resume`).

7. **Node statuses:** Adopt the v3 status set: `pending`, `in_progress`,
   `completed`, `failed`, `blocked`, `cost_blocked`, `merge_blocked`. Keep
   `skipped` for backward compatibility with the current planning logic.

8. **Scope boundary:** This spec is strictly a persistence-layer swap. The
   planning algorithm (graph construction, archetype injection, topological
   sort) is unchanged. Planning algorithm changes come in a separate spec.

## Non-Goals

- Changing the planning algorithm, graph construction, or archetype injection.
- Implementing v3's content-hash-based affected-group reset.
- Adding new CLI commands beyond updating existing ones.
- Modifying the knowledge store tables (memory_facts, etc.).
- Changing how `tasks.md` is authored or parsed.
