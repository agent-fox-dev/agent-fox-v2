# PRD: Planning Engine

**Source:** `.specs/prd.md` -- Section 5 "Planning" (REQ-010 through REQ-016),
Section 4 "Plan and Execute" workflow, Section 6 (fast mode, coordinator model).

## Overview

The planning engine discovers specification folders, parses task definitions
from markdown files, constructs a dependency-aware task graph, resolves
execution order via topological sort, and persists the plan as JSON for
downstream commands (`code`, `status`). It is the bridge between human-written
specs and machine-executed sessions.

## Problem Statement

Before the orchestrator can execute coding sessions, it needs to know *what*
to execute and *in what order*. Specifications are authored as markdown files
across multiple folders. The planning engine must read these files, build a
directed acyclic graph (DAG) of task groups respecting both intra-spec
sequential ordering and cross-spec dependency declarations, and persist the
result so that execution, status, and reset commands can operate on it.

## Goals

- Discover spec folders in `.specs/` and identify their task definitions
- Parse `tasks.md` checkbox-format markdown into structured task group objects
- Build a task graph with nodes (task groups) and edges (dependencies)
- Resolve execution order via topological sort with cycle detection
- Support fast mode: exclude optional tasks and rewire dependencies
- Support single-spec planning via `--spec` filter
- Support `--reanalyze` to discard cached dependency ordering
- Persist the plan as `.agent-fox/plan.json`
- Expose via `agent-fox plan` CLI command

## Non-Goals

- Executing coding sessions -- that is spec 03/04
- Validating spec quality (missing files, oversized groups) -- that is spec 09
- AI-assisted dependency verification (REQ-016 background check) -- deferred
  to a future iteration; the CLI flag is accepted but prints a "not yet
  implemented" message
- Hot-loading new specs during execution -- that is spec 04

## Key Decisions

- **Task graph nodes = task groups, not subtasks.** A task group (e.g., "2.
  Implement config system") is the scheduling unit. Subtasks within a group
  are the agent's checklist within a single session.
- **Intra-spec ordering is implicit.** Task group N depends on group N-1
  within the same spec. No explicit declaration needed.
- **Cross-spec dependencies come from the PRD dependency table.** Each spec's
  `prd.md` declares a dependency table mapping `From Group -> To Group` across
  specs. The planning engine reads these and adds edges.
- **Plan persistence format is JSON.** The plan is saved at
  `.agent-fox/plan.json` with the full graph serialized: nodes, edges, and
  metadata (creation time, fast-mode flag, filtered spec).
- **Fast mode uses `*` marker.** Tasks with `*` after the checkbox
  (e.g., `- [ ] * 3. Polish`) are optional. Fast mode removes them and
  rewires dependencies so the graph stays connected.
- **NodeStatus tracks lifecycle.** Each node carries a status enum:
  `pending`, `in_progress`, `completed`, `failed`, `blocked`, `skipped`.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 01_core_foundation | 5 | 1 | CLI framework (Click group, `main`), `AgentFoxConfig`, `PlanError`, `ConfigError`, `load_config()`, `AppTheme` |
