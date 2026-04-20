# Requirements Document: Plan Analysis and Dependency Quality

## Introduction

This document specifies parallelism analysis for the plan command, critical
path computation, new spec validation rules for dependency quality, and
auto-fix capabilities for mechanically fixable findings. It extends the
planning engine (spec 02) and specification validation (spec 09).

## Glossary

| Term | Definition |
|------|-----------|
| Phase | A set of nodes that can execute concurrently -- all nodes in a phase have the same earliest-start time |
| Critical path | The longest chain of dependent nodes from any source to any sink in the task graph; determines the minimum possible execution time |
| Float | The amount a node's start can be delayed without delaying the project: `latest_start - earliest_start` |
| Peak parallelism | The maximum number of nodes in any single phase |
| Earliest start (ES) | The earliest time a node can begin, computed as `max(ES(pred) + 1)` for all predecessors |
| Latest start (LS) | The latest time a node can begin without delaying the project, computed backward from the sink |
| Coarse dependency | A cross-spec dependency declared using the standard format (`\| This Spec \| Depends On \|`), which resolves to last-group-to-first-group and prevents fine-grained parallelism |
| Group-level dependency | A cross-spec dependency declared using the alternative format (`\| Spec \| From Group \| To Group \|`), which enables finer-grained parallelism |
| Fixable finding | A lint finding whose correction is mechanical and can be applied automatically without human judgment |

## Requirements

### Requirement 1: Parallelism Analysis

**User Story:** As a developer, I want to see which tasks can run in
parallel and how many workers I can saturate so I can choose the right
`--parallel` value for `agent-fox code`.

#### Acceptance Criteria

1. [20-REQ-1.1] WHEN the `--analyze` flag is passed to `agent-fox plan`,
   THE system SHALL compute and display a phase-grouped parallelism timeline
   showing which nodes can execute concurrently.

2. [20-REQ-1.2] THE parallelism timeline SHALL group nodes into phases where
   each phase contains all nodes with the same earliest-start time, and
   phases are listed in ascending order of earliest-start time.

3. [20-REQ-1.3] FOR EACH phase, THE system SHALL display the phase number,
   the number of concurrent nodes (worker count), and the list of node IDs
   with their titles.

4. [20-REQ-1.4] THE system SHALL display a summary line showing the total
   number of phases, the peak worker count (maximum nodes in any phase), and
   the total number of nodes.

#### Edge Cases

1. [20-REQ-1.E1] IF the task graph is empty (no nodes), THEN THE system
   SHALL display "No tasks to analyze" and return without error.

2. [20-REQ-1.E2] IF all nodes form a single chain (zero parallelism), THEN
   THE system SHALL show each node in its own phase with worker count 1.

---

### Requirement 2: Critical Path Computation

**User Story:** As a developer, I want to know which tasks are on the
critical path so I know where delays will directly impact project completion.

#### Acceptance Criteria

1. [20-REQ-2.1] WHEN the `--analyze` flag is passed, THE system SHALL
   compute the critical path: the longest chain of dependent nodes from any
   source to any sink in the task graph.

2. [20-REQ-2.2] THE system SHALL display the critical path as an ordered
   list of node IDs, along with its length (number of nodes).

3. [20-REQ-2.3] FOR EACH node in the task graph, THE system SHALL compute
   the float (latest_start - earliest_start) and identify nodes with zero
   float as critical-path nodes.

4. [20-REQ-2.4] THE system SHALL display a float summary listing specs or
   nodes with the most float, helping users identify work that has scheduling
   flexibility.

#### Edge Cases

1. [20-REQ-2.E1] IF multiple paths share the same maximum length (tied
   critical paths), THE system SHALL display any one of them and note that
   alternative critical paths exist.

---

### Requirement 3: Coarse Dependency Lint Rule

**User Story:** As a spec author, I want to be warned when my dependency
table uses the coarse spec-level format so I can switch to group-level
granularity and enable better parallelism.

#### Acceptance Criteria

1. [20-REQ-3.1] THE lint-spec command SHALL include a `coarse-dependency`
   validation rule that detects cross-spec dependencies declared using the
   standard table format (`| This Spec | Depends On |`).

2. [20-REQ-3.2] FOR EACH spec that uses the standard dependency format, THE
   system SHALL produce a Warning-severity finding recommending the
   group-level format (`| Spec | From Group | To Group |`).

3. [20-REQ-3.3] THE finding message SHALL explain that the standard format
   resolves to last-group-to-first-group, which may serialize work that
   could run in parallel.

#### Edge Cases

1. [20-REQ-3.E1] IF a spec's prd.md has no dependency table at all, THEN
   THE system SHALL produce no finding for this rule (no dependencies means
   no coarseness issue).

2. [20-REQ-3.E2] IF a spec's prd.md uses the group-level format, THEN THE
   system SHALL produce no finding for this rule.

---

### Requirement 4: Circular Dependency Lint Rule

**User Story:** As a spec author, I want circular dependencies caught at
lint time so I do not discover them only when running `agent-fox plan`.

#### Acceptance Criteria

1. [20-REQ-4.1] THE lint-spec command SHALL include a `circular-dependency`
   validation rule that detects dependency cycles across all specs.

2. [20-REQ-4.2] THE rule SHALL construct a lightweight directed graph from
   all specs' prd.md dependency tables (spec-level, not group-level) and
   check for cycles.

3. [20-REQ-4.3] WHEN a cycle is detected, THE system SHALL produce an
   Error-severity finding listing the specs involved in the cycle.

#### Edge Cases

1. [20-REQ-4.E1] IF a dependency table references a spec that does not exist
   in the discovered set, THE rule SHALL skip that edge (the existing
   `broken-dependency` rule already catches this).

2. [20-REQ-4.E2] IF no dependency tables exist across all specs, THEN THE
   system SHALL produce no finding for this rule.

---

### Requirement 5: af-spec Dependency Granularity Guidance

**User Story:** As a developer using the af-spec skill, I want the skill to
select the earliest sufficient upstream group for each dependency so the
generated specs maximize parallelism.

#### Acceptance Criteria

1. [20-REQ-5.1] THE af-spec skill's Step 2 (Learn the Context) SHALL
   instruct the LLM to identify the earliest group in each upstream spec
   that produces the artifact being depended on, rather than depending on
   the last group.

2. [20-REQ-5.2] THE af-spec skill SHALL always generate cross-spec
   dependency tables using the group-level format
   (`| Spec | From Group | To Group | Relationship |`), never the standard
   format.

3. [20-REQ-5.3] FOR EACH dependency declared, THE af-spec skill SHALL
   include a brief justification in the Relationship column explaining why
   the chosen upstream group is the earliest sufficient one.

#### Edge Cases

1. [20-REQ-5.E1] IF the upstream spec has not yet been written (no tasks.md
   exists), THEN THE af-spec skill SHALL use group 0 as a sentinel and note
   that the dependency will be resolved when the upstream spec is created.

---

### Requirement 6: Auto-Fix for Lint Findings

**User Story:** As a spec author, I want lint-spec to automatically fix
mechanical problems so I do not have to manually edit every file.

#### Acceptance Criteria

1. [20-REQ-6.1] THE `lint-spec` command SHALL accept a `--fix` flag that
   automatically applies corrections for fixable findings.

2. [20-REQ-6.2] WHEN `--fix` is provided, THE system SHALL first detect all
   findings normally, then apply fixers for eligible findings, then
   re-validate and output the remaining (unfixed) findings.

3. [20-REQ-6.3] THE `coarse-dependency` fixer SHALL rewrite each standard-
   format dependency table to the group-level format. For each row, it SHALL
   look up the upstream spec's task groups and use the last group number as
   From Group and the current spec's first group number as To Group. The
   original description column SHALL be preserved as the Relationship column.

4. [20-REQ-6.4] THE `missing-verification` fixer SHALL append a verification
   step (`N.V Verify task group N`) with standard checklist sub-items to each
   task group that lacks one.

5. [20-REQ-6.5] AFTER applying all fixes, THE system SHALL print a summary
   line listing how many findings were fixed, grouped by rule name.

6. [20-REQ-6.6] THE `--fix` flag SHALL be compatible with all output formats
   (`--format table|json|yaml`). The fix summary is printed to stderr; the
   post-fix findings go to stdout in the requested format.

#### Edge Cases

1. [20-REQ-6.E1] IF no fixable findings exist, THEN `--fix` SHALL behave
   identically to a normal lint run (no files modified, no fix summary).

2. [20-REQ-6.E2] IF the upstream spec referenced by a coarse-dependency row
   has no tasks.md (group numbers unknown), THEN the fixer SHALL use 0 as
   the From Group sentinel and note this in the Relationship column.

3. [20-REQ-6.E3] IF a file cannot be written (permission error, read-only),
   THEN the fixer SHALL log a warning for that file, skip it, and continue
   with other fixes.

4. [20-REQ-6.E4] UNFIXABLE findings (circular-dependency, broken-dependency,
   oversized-group) SHALL be unaffected by `--fix` and SHALL remain in the
   post-fix output.
