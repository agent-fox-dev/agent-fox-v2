# PRD: --dry-run Flag on plan Command

## Problem

The `agent-fox plan` command always persists the plan to DuckDB on every
invocation. There is no way for a user to preview the execution plan — including
parallelism phases, dependency edges, and critical path — without modifying the
database. Users want a dry-run mode to understand the plan structure before
committing it.

## Feature

Add a `--dry-run` flag to the `plan` command. When set, the command runs the
full planning pipeline (discovery → parsing → building → resolving) but
**skips database persistence**. It then displays a richer analysis than the
standard summary:

1. **Standard summary** — spec names, task count, dependency count, execution
   order (same as today).
2. **Parallelism phases** — groups of tasks that can execute concurrently in
   each scheduling wave.
3. **Dependency edges** — explicit list of edges showing which nodes depend on
   which, grouped by type (intra-spec vs. cross-spec).
4. **Critical path** — the longest dependency chain from first to last node.

### Flag Behavior

- `--dry-run` is a boolean flag (default off).
- Composable with `--fast` and `--spec` — they modify the plan before analysis,
  just as they do for a normal plan run.
- Composable with `--json` — produces structured JSON output of the analysis
  (no DB persistence).
- When `--dry-run` is set, the plan is **not** persisted to DuckDB.
- Exit code 0 on success, 1 on plan error (same as normal plan).

### API Support

The `run_plan()` function in `planner.py` gains an `dry_run: bool = False`
parameter. When `dry_run=True`, it builds the plan and returns the `TaskGraph`
without persisting to DuckDB. The analysis formatting is a separate concern
handled by the caller (CLI or otherwise).

## Design Decisions

1. **Parallelism phases are derived from topological layers.** A "phase" is a
   maximal set of nodes whose predecessors are all in earlier phases. This is
   computed from the resolved order and the edge set — no new graph algorithm is
   needed beyond grouping nodes by their topological depth.

2. **Critical path uses longest-path computation on the DAG.** Since the graph
   is acyclic, the critical path is the longest path from any source node to
   any sink node (using uniform edge weights). This gives users the bottleneck
   chain. If multiple paths tie, report one deterministically (lexicographic
   tie-break on node IDs).

3. **Analysis output is a new formatter, not a modification to
   `format_plan_summary`.** The existing summary remains unchanged. A new
   `format_plan_analysis` function produces the richer output. This keeps the
   default `plan` output unchanged and avoids breaking existing workflows.

4. **JSON analysis output includes all four sections** (summary, phases,
   edges, critical path) as top-level keys alongside the existing JSON
   structure (nodes, edges, order, metadata).

5. **No new database tables or schema changes.** The `--dry-run` flag only
   affects the CLI and planner layers — it suppresses persistence, not changes
   schema.

6. **The analyzer module lives at `agent_fox/graph/analyzer.py`.** A previous
   analyzer module at this path was deleted in spec 63 when plan caching was
   removed. This spec reintroduces a simpler, focused module at the same path
   with only the three analysis functions (phases, critical path, edges
   grouping).

## Source

Source: https://github.com/agent-fox-dev/agent-fox/issues/593
