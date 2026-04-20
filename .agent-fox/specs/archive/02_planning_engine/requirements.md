# Requirements Document: Planning Engine

## Introduction

This document specifies the planning engine for agent-fox v2: specification
discovery, task definition parsing, task graph construction, dependency
resolution, fast-mode filtering, plan persistence, and the `agent-fox plan`
CLI command. It depends on the core foundation established by spec 01.

## Glossary

| Term | Definition |
|------|-----------|
| Spec folder | A directory under `.specs/` named `NN_name/` containing specification files |
| Task group | A top-level numbered entry in `tasks.md` (e.g., `- [ ] 1. Write failing tests`). The atomic scheduling unit. |
| Subtask | A nested checkbox entry within a task group. Executed within a single session, not scheduled independently. |
| Task graph | A directed acyclic graph (DAG) where nodes are task groups and edges are dependency relationships |
| Topological sort | An ordering of graph nodes such that every node appears after all its predecessors |
| Fast mode | A planning mode that excludes optional tasks (marked with `*`) and rewires dependencies |
| Plan | The persisted execution plan at `.agent-fox/plan.json` containing the full task graph |
| Node ID | A unique identifier for a task group: `{spec_name}:{group_number}` (e.g., `01_core_foundation:3`) |
| Optional task | A task group marked with `*` in `tasks.md`, excluded during fast-mode planning |

## Requirements

### Requirement 1: Specification Discovery

**User Story:** As a developer, I want the planning engine to automatically
find all specification folders so I do not have to list them manually.

#### Acceptance Criteria

1. [02-REQ-1.1] WHEN the plan command is run, THE system SHALL scan the
   `.specs/` directory for subdirectories matching the pattern `NN_name/`
   (two-digit prefix, underscore, descriptive name) and return them sorted
   by their numeric prefix.

2. [02-REQ-1.2] WHERE the `--spec` option is provided, THE system SHALL
   restrict discovery to the single named specification and ignore all others.

3. [02-REQ-1.3] WHEN a discovered spec folder does not contain a `tasks.md`
   file, THE system SHALL skip it with a logged warning.

#### Edge Cases

1. [02-REQ-1.E1] IF the `.specs/` directory does not exist or is empty, THEN
   THE system SHALL raise a `PlanError` with a message indicating no
   specifications were found.

2. [02-REQ-1.E2] IF the `--spec` value does not match any discovered folder,
   THEN THE system SHALL raise a `PlanError` listing available spec names.

---

### Requirement 2: Task Definition Parsing

**User Story:** As a developer, I want my `tasks.md` checkbox-format markdown
parsed into structured task definitions so the planner can reason about them.

#### Acceptance Criteria

1. [02-REQ-2.1] THE parser SHALL extract top-level task groups from `tasks.md`
   where each group starts with `- [ ] N. ` or `- [x] N. ` (checkbox followed
   by a group number and period).

2. [02-REQ-2.2] THE parser SHALL extract nested subtasks (indented checkboxes)
   and associate them with their parent task group.

3. [02-REQ-2.3] THE parser SHALL detect the optional marker `*` after the
   checkbox (e.g., `- [ ] * 3. Polish`) and flag the task group as optional.

4. [02-REQ-2.4] THE parser SHALL extract the task group title (text after the
   group number) and the full body text (all lines until the next top-level
   group) for each task group.

#### Edge Cases

1. [02-REQ-2.E1] IF a `tasks.md` file contains no parseable task groups, THEN
   THE parser SHALL return an empty list and log a warning.

2. [02-REQ-2.E2] IF task group numbers are not contiguous (e.g., 1, 3, 5),
   THE parser SHALL accept them as-is without error.

---

### Requirement 3: Task Graph Construction

**User Story:** As a developer, I want the planner to build a dependency graph
from my specs so that tasks execute in the correct order.

#### Acceptance Criteria

1. [02-REQ-3.1] WITHIN a specification, THE system SHALL create sequential
   dependency edges: group N depends on group N-1 (for N > 1).

2. [02-REQ-3.2] ACROSS specifications, THE system SHALL read cross-spec
   dependency declarations from each spec's `prd.md` dependency table and
   create the corresponding edges.

3. [02-REQ-3.3] THE system SHALL assign each node a unique ID in the format
   `{spec_name}:{group_number}` (e.g., `02_planning_engine:1`).

4. [02-REQ-3.4] THE system SHALL initialize all nodes with status `pending`.

#### Edge Cases

1. [02-REQ-3.E1] IF a cross-spec dependency references a spec or group that
   does not exist in the discovered set, THEN THE system SHALL raise a
   `PlanError` identifying the dangling reference.

2. [02-REQ-3.E2] IF the constructed graph contains a cycle, THEN THE system
   SHALL raise a `PlanError` listing the nodes involved in the cycle.

---

### Requirement 4: Dependency Resolution

**User Story:** As a developer, I want the planner to produce a valid
execution order so that every task runs after its prerequisites.

#### Acceptance Criteria

1. [02-REQ-4.1] THE system SHALL produce a topological ordering of all task
   graph nodes such that for every edge (A -> B), A appears before B in
   the ordering.

2. [02-REQ-4.2] WHEN multiple nodes have no unresolved dependencies, THE
   system SHALL order them by spec prefix (ascending), then by group number
   (ascending) for deterministic output.

#### Edge Cases

1. [02-REQ-4.E1] IF the graph is empty (no task groups found), THEN THE
   system SHALL produce an empty ordering and warn the user.

---

### Requirement 5: Fast-Mode Filtering

**User Story:** As a developer, I want to skip optional tasks when I need a
faster build, while keeping the dependency graph valid.

#### Acceptance Criteria

1. [02-REQ-5.1] WHERE fast mode is enabled, THE system SHALL remove all
   nodes flagged as optional from the task graph and set their status to
   `skipped`.

2. [02-REQ-5.2] WHERE an optional node B sits between nodes A and C (A -> B
   -> C), THE system SHALL rewire the dependency so that C depends directly
   on A.

3. [02-REQ-5.3] WHERE fast mode is enabled, THE system SHALL record the
   fast-mode flag in the persisted plan metadata.

---

### Requirement 6: Plan Persistence

**User Story:** As a developer, I want the plan saved to disk so that other
commands can use it without re-planning.

#### Acceptance Criteria

1. [02-REQ-6.1] THE system SHALL serialize the task graph (nodes, edges,
   metadata) as JSON and write it to `.agent-fox/plan.json`.

2. [02-REQ-6.2] THE system SHALL include metadata: creation timestamp (ISO
   8601), fast-mode flag, filtered spec name (if any), and the agent-fox
   version.

3. [02-REQ-6.3] WHEN a plan already exists and `--reanalyze` is NOT set,
   THE system SHALL load and return the existing plan instead of rebuilding.

4. [02-REQ-6.4] WHEN `--reanalyze` is set, THE system SHALL discard the
   existing plan and rebuild from scratch.

#### Edge Cases

1. [02-REQ-6.E1] IF the existing `plan.json` is corrupted or unparseable,
   THEN THE system SHALL log a warning, discard it, and rebuild.

---

### Requirement 7: Plan CLI Command

**User Story:** As a developer, I want an `agent-fox plan` command that
builds and displays the execution plan.

#### Acceptance Criteria

1. [02-REQ-7.1] THE CLI SHALL register an `agent-fox plan` subcommand that
   triggers planning and prints a summary (total tasks, specs, dependencies,
   execution order).

2. [02-REQ-7.2] THE CLI SHALL accept `--fast` to enable fast-mode filtering.

3. [02-REQ-7.3] THE CLI SHALL accept `--spec NAME` to restrict planning to
   a single specification.

4. [02-REQ-7.4] THE CLI SHALL accept `--reanalyze` to force a fresh plan.

5. [02-REQ-7.5] THE CLI SHALL accept `--verify` and print a "not yet
   implemented" message (placeholder for REQ-016).
