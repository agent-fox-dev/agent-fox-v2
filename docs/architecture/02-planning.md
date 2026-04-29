# Planning — From Specs to Task Graphs

## Purpose and Placement

Planning is the bridge between human intent (specs) and machine execution
(coding sessions). The planner reads the spec artifacts described in
[Part 1: Spec Authoring](01-spec-authoring.md), constructs a directed acyclic
graph of tasks with dependency edges, injects review and validation agents at
the right points, computes an execution order, and persists the result. The
output — persisted to DuckDB — is what the engine consumes when `agent-fox code` runs
(see [Part 3: Execution and Archetypes](03-execution-and-archetypes.md)).

The planner is deterministic. Given the same specs and configuration, it
produces the same graph. There is no LLM inference in the planning phase —
every decision is mechanical. This is deliberate: the plan is the contract
between the human (who authored the specs) and the machine (which will execute
them). Making it deterministic means the human can inspect, predict, and trust
the plan without reasoning about probabilistic behavior.

---

## Conceptual Model

The task graph is a DAG where nodes represent units of work and edges represent
"must complete before" relationships. Each node corresponds to either a task
group from `tasks.md` or an automatically injected archetype agent (a review or
validation step that the system adds without the author declaring it).

The graph has three kinds of structure:

- **Intra-spec chains**: Within a single spec, task groups execute sequentially
  by group number. Group 1 must complete before group 2 starts. This is the
  default ordering inherited from the linear structure of `tasks.md`.

- **Cross-spec edges**: Dependencies declared in `prd.md` create edges between
  groups in different specs. These are the only mechanism for expressing that
  work in one spec depends on work in another.

- **Injected archetype nodes**: The system automatically adds review and
  validation agents at configurable positions in each spec's chain. These nodes
  are not authored by the human — they are added by the planner based on the
  archetype configuration.

The combination of these three structures produces a DAG that can be
topologically sorted into an execution order. The sort is deterministic: ties
are broken by spec name (alphabetically) then group number (ascending).

---

## Graph Construction

Graph construction is a four-phase process.

### Phase 1: Base Nodes and Intra-Spec Edges

For each spec with a `tasks.md` file, the planner parses task groups and creates
one node per group. Each node carries the spec name, group number, completion
state (from the checkbox), optional flag, subtask count, and body text.

Consecutive groups within a spec are connected by intra-spec edges: the node for
group N is a predecessor of the node for group N+1. This creates a linear chain
per spec, reflecting the sequential nature of the task list.

Nodes that are already marked complete in `tasks.md` (checkbox state `[x]`)
start in the COMPLETED state. The engine will skip them during execution but
their completion status still satisfies dependency edges — downstream nodes see
them as done.

### Phase 2: Archetype Injection

The planner injects non-coder agent nodes at three positions in each spec's
chain, based on the archetype configuration:

**Pre-execution agents** (injection point: `auto_pre`) are added at group 0,
before the first coder group. Currently this includes the Reviewer in
pre-review mode (spec quality review) and drift-review mode (design-to-code
drift detection). These agents examine the spec and existing codebase before
any implementation begins, providing early warning of problems.

The drift-review node has a gating rule: if the spec references no files that
currently exist in the repository (determined by scanning `design.md` for file
paths and checking the filesystem), the node is skipped. There is nothing to
validate drift against if the code does not yet exist.

**Mid-execution agents** (injection point: `auto_mid`) are added after
test-writing groups. Currently this is the Reviewer in audit-review mode, which
validates that the tests written in earlier groups actually cover the test spec
contracts. The audit-review node is only injected if the spec's `test_spec.md`
contains at least a configurable minimum number of test entries — below that
threshold, auditing has insufficient material to work with.

**Post-execution agents** (injection point: `auto_post`) are added after the
last coder group. Currently this is the Verifier, which runs the test suite and
checks each requirement against the implemented code.

Injected nodes are wired into the dependency chain with appropriate edges: a
pre-execution node precedes the first coder group, a post-execution node follows
the last coder group, and mid-execution nodes are spliced between the relevant
groups.

### Phase 3: Archetype Tag Overrides

After injection, the planner applies archetype tag overrides from `tasks.md`.
If a task group carries an `[archetype: skeptic]` tag, that group's node is
reassigned from the default "coder" archetype to "skeptic." These tags are the
highest-priority assignment mechanism — they override both the builder's default
("coder" for all non-injected nodes) and the automatic injection rules.

This enables spec authors to place review or validation steps at arbitrary
points in their task sequence, not just at the three automatic injection points.

### Phase 4: Cross-Spec Edges

Cross-spec dependencies parsed from `prd.md` files create edges between nodes
in different specs. If spec A's group 3 depends on spec B's group 2, an edge is
added from B:2 to A:3 — B:2 must complete before A:3 can start.

Standard-format dependencies (which declare spec-level rather than group-level
dependencies) use sentinel group numbers that resolve to the first or last
actual group in the referenced spec. This means "depends on spec B" becomes
"depends on the last group of spec B," which is conservative but correct.

The planner validates that both endpoints of each cross-spec edge exist in the
graph. References to nonexistent specs or group numbers are rejected during
spec validation (see [Part 1](01-spec-authoring.md)), but the planner
performs a second check as a safety net.

---

## Execution Order

The graph is topologically sorted using Kahn's algorithm to produce a linear
execution order. The algorithm processes nodes with zero in-degree (no unsatisfied
dependencies) first, adding them to the order and decrementing the in-degree of
their successors.

**Deterministic tie-breaking** is critical. When multiple nodes have zero
in-degree simultaneously, the algorithm must choose one. Agent-fox uses a
min-heap keyed by (spec_name, group_number), which produces alphabetical
ordering by spec with ascending group numbers within each spec. This means the
execution order is fully reproducible across runs.

**Cycle detection** is a byproduct of the algorithm. If the final order contains
fewer nodes than the graph, there is a cycle — some nodes could never reach zero
in-degree. The planner raises an error listing the involved nodes. Note that
spec-level cycles are also caught during validation, but group-level cycles
(which can arise from complex cross-spec dependencies) are only detectable here.

---

## Fast Mode

Fast mode is an alternative planning strategy for situations where speed matters
more than completeness. When enabled, the planner identifies all optional nodes
(those with the optional flag from `tasks.md`) and removes them from the
execution order.

Removal is non-destructive: optional nodes remain in the graph with a SKIPPED
status, but they are excluded from the execution order. Their dependency edges
are rewired — each predecessor of an optional node gets a new edge to each of
its successors, preserving the reachability of downstream nodes.

The graph's metadata records whether fast mode was applied, so the engine knows
how to interpret SKIPPED nodes.

---

## File Impact Analysis

Before parallel dispatch, the engine needs to know which task groups might
modify the same files. The file impact analyzer scans `tasks.md` and `design.md`
for backtick-quoted file paths, using regex patterns that match common source
file extensions. This produces a predicted set of affected files per node.

Conflict detection compares these sets pairwise. If two nodes predict
overlapping file modifications, they are considered conflicting and should not
run in parallel — doing so risks merge conflicts when their worktree branches
are integrated back into `develop`.

This analysis is predictive, not authoritative. A node might modify files not
mentioned in the spec, or might not modify a file that the spec references.
The system errs on the side of caution: nodes with no predicted files are
treated as non-conflicting (they cannot be assessed), while nodes with overlapping
predictions are serialized.

---

## Ready Task Ordering

When multiple tasks are simultaneously ready, the dispatcher uses spec-fair
round-robin to prevent any single spec from monopolizing all parallel slots.
Tasks are grouped by spec (sorted by numeric prefix), and the dispatcher
interleaves one task from each spec per round. Within a spec, tasks are
sorted by predicted duration descending — longest tasks dispatch first to
minimize wall-clock time. Fan-out weights bias ordering toward specs
whose downstream dependents are most impactful — unblocking a spec with many
successors is higher priority than one with few.

---

## Graph Persistence

The task graph is persisted in the DuckDB knowledge store across three tables:
`plan_nodes` (node attributes), `plan_edges` (source/target pairs with edge
kind), and `plan_meta` (content hash, version, fast mode flag, filtered spec).
The plan is rebuilt from `.agent-fox/specs/` on every `agent-fox plan` invocation and
written atomically.

Persistence is designed for forward compatibility. Missing fields receive
sensible defaults — for example, `archetype` defaults to "coder" and
`instances` defaults to 1. This allows plans built by older versions to be
loaded by newer versions without error.

The engine loads the plan at startup, potentially injecting missing archetype
nodes if the archetype configuration has changed since the plan was built. This
runtime injection ensures that cached plans stay usable even as archetype
settings evolve, without requiring a full replan.

---

## Runtime Graph Patching

The plan is not entirely static. The engine can modify the graph at runtime in
two ways:

**Archetype injection patching**: If the loaded plan was built with a different
archetype configuration than the current one (for example, audit-review was
disabled when the plan was built but is now enabled), the engine injects the
missing archetype nodes into the live graph, adds the appropriate edges, and
updates the execution order. The updated plan is persisted back to DuckDB so
the injected nodes survive a restart.

**Hot-load discovery**: During sync barriers (periodic pauses in execution),
the engine checks for new specs that have appeared in `.agent-fox/specs/` since the plan
was built. A new spec must pass four gates before admission: it is git-tracked
on develop, it contains all five core artifacts (non-empty), it passes lint
validation with no error-severity findings, and it is not already fully
implemented (all task groups complete). Specs that pass are added to the live
graph. This enables long-running sessions to pick up new work without a manual
replan.

---

## Review-Only Plans

For situations where the operator wants to run review agents without any coding,
the planner can build a review-only graph. This graph contains only Reviewer
and Verifier nodes — no coder nodes. It scans the specs directory,
creates review nodes for specs that have existing source files or requirements,
and produces a minimal graph suitable for a read-only analysis pass.

---

*Previous: [Spec Authoring and Spec Structure](01-spec-authoring.md)*
*Next: [Execution and Archetypes](03-execution-and-archetypes.md)*
