# PRD: Plan Analysis and Dependency Quality

## Overview

Extend the planning engine and specification validation with parallelism
analysis, critical path computation, dependency quality checks, and auto-fix
capabilities. Give users actionable visibility into how their dependency
declarations affect execution time, catch common authoring mistakes that
silently serialize work, and automatically fix the problems where possible.

## Problem Statement

The planning engine (spec 02) builds a correct DAG and resolves execution
order, but provides no insight into *parallelism*. Users cannot see which
specs gate the project, which tasks sit on the critical path, or how many
workers can be saturated at peak. The only way to get this information today
is to manually trace the plan.json graph (as done in investigation.md).

On the authoring side, the af-spec skill and lint-spec command have no
checks for dependency granularity. A spec author who uses the coarse
`| This Spec | Depends On |` table format unknowingly serializes work that
could run concurrently. Nothing warns about this, and nothing prevents
circular dependencies until `agent-fox plan` is run.

When lint-spec does catch problems, the user must manually fix every finding.
For structural issues like coarse dependency tables and missing verification
steps, the fix is mechanical and can be automated.

## Goals

- Add a `--analyze` flag to `agent-fox plan` that prints a parallelism
  timeline (phase grouping) and critical path summary
- Compute critical path length, total float per node, and peak worker count
- Add a `coarse-dependency` lint rule to warn when specs use the standard
  (spec-level) dependency format instead of the group-level format
- Add a `circular-dependency` lint rule that detects cycles across all specs'
  dependency tables without requiring a full plan build
- Add a `--fix` flag to `lint-spec` that automatically rewrites fixable
  findings in place, then re-validates to confirm the fix
- Update the af-spec skill to instruct the LLM to select the earliest
  sufficient upstream group for each dependency

## Non-Goals

- Changing the plan execution engine (spec 04) -- this spec only adds
  analysis and validation
- Adding runtime parallelism metrics or profiling
- Automatic dependency inference from code imports (would require AI
  analysis of source code)
- Intra-spec parallelism (splitting a spec's sequential chain into
  independent sub-graphs)
- Auto-fixing circular dependencies or broken dependencies (these require
  human judgment about which edge to remove or which spec to reference)

## Key Decisions

- **Phase grouping uses BFS level sets.** A phase is the set of nodes whose
  earliest-start time is the same. This naturally groups concurrently
  executable work.
- **Critical path uses longest-path DAG algorithm.** Each node has unit
  weight (one task group = one unit of work). The critical path is the
  longest chain from any source to any sink.
- **Float is computed as latest_start - earliest_start.** Nodes with zero
  float are on the critical path.
- **Coarse-dependency is a Warning, not an Error.** The standard format is
  valid and produces correct plans -- it is just suboptimal for parallelism.
- **Circular-dependency detection reads prd.md tables only.** It does not
  need a full plan build. It constructs a lightweight spec-level graph from
  dependency tables and runs cycle detection.
- **`--fix` modifies files in place.** Fixers read the file, apply the
  transformation, and write back. Only Warning-severity findings with
  mechanical fixes are eligible. Error-severity findings (like circular
  dependencies) require human judgment. The flag outputs a summary of what
  was fixed and what remains.
- **`--fix` re-validates after applying fixes.** After all fixers run,
  lint-spec re-runs validation and outputs the remaining findings. This
  confirms fixes were applied correctly and shows the user what (if
  anything) still needs manual attention.
- **af-spec guidance is a prompt-only change.** No code changes to the skill
  runner -- only the SKILL.md instructions are updated.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 02_planning_engine | 4 | 1 | Uses `TaskGraph`, `Edge`, `Node`, `resolve_order()` for analysis algorithms |
| 09_spec_validation | 2 | 3 | Extends `validate_specs()` with new lint rules; uses `Finding`, `Severity` types |
| 01_core_foundation | 1 | 1 | Uses `PlanError` for error reporting |
