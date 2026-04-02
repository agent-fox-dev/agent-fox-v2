# PRD: Plan Always Rebuild

## Problem

The `agent-fox plan` command uses a cache layer (`plan.json`) to avoid
rebuilding the task graph on repeated invocations. A `--reanalyze` flag exists
to bypass the cache and force a rebuild.

In practice, the cache provides negligible benefit: plan building is a purely
local operation (file I/O and in-memory graph construction, no API calls) that
completes in milliseconds. The cache adds complexity:

- `_compute_specs_hash()` and `_compute_config_hash()` functions
- `_cache_matches_request()` validation logic
- `specs_hash` and `config_hash` metadata fields on `PlanMetadata`
- The `--reanalyze` CLI flag and associated branching

The cache also has a subtle downside: it can serve a stale plan if the
invalidation heuristics miss a relevant change.

## Solution

Remove the plan cache from the `plan` CLI command:

1. The `plan` command always rebuilds the task graph from `.specs/`.
2. The `--reanalyze` CLI option is removed (the default behavior is now
   equivalent to `--reanalyze`).
3. All dead code supporting cache invalidation is removed:
   `_compute_specs_hash()`, `_compute_config_hash()`,
   `_cache_matches_request()`, and the `specs_hash`/`config_hash` fields on
   `PlanMetadata`.
4. The `plan` command still persists the built graph to `plan.json` (the
   engine's `run` command reads it).
5. Node statuses in the rebuilt plan reflect actual state, derived from
   `tasks.md` checkbox parsing (the builder already does this via
   `NodeStatus.COMPLETED if group.completed else NodeStatus.PENDING`).

## Non-Goals

- Changing how the engine (`run` command) loads or uses `plan.json`.
- Changing plan persistence (`save_plan` / `load_plan`).
- Changing `PlanMetadata` fields beyond removing `specs_hash` and
  `config_hash`.

## Supersedes

- `02_planning_engine` requirements 02-REQ-6.3 (cache reuse) and 02-REQ-6.4
  (`--reanalyze` flag) are superseded by this spec. Requirements 02-REQ-6.1
  (plan serialization) and 02-REQ-6.2 (metadata) remain in effect.
