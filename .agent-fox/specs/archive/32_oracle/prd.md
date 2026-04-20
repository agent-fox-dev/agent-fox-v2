# PRD: Oracle Agent Archetype

## Problem

When a new spec is drafted, its design decisions are made based on the state of
the code at the point in time the spec is written. If the spec is not
implemented immediately, assumptions made about the codebase may no longer be
true once the spec is finally implemented.

Specs reference concrete codebase artifacts -- file paths, function names,
class names, variable names, module structures, API signatures, and data model
shapes. Between spec authoring and spec execution, other specs may be
implemented that rename, move, or delete these artifacts, or change their
behavioral contracts.

Without validation, the coder agent receives a spec full of stale references
and incorrect assumptions, leading to wasted sessions, incorrect
implementations, and cascading failures.

## Solution

Introduce an **Oracle** agent archetype that validates a spec's assumptions
against the current codebase state before coding begins. The oracle performs a
**full assumption audit**: it checks identifier references (file paths,
function/class/variable names), design assumptions (module responsibilities,
API signatures, data flow), and behavioral assumptions (return formats, error
handling contracts).

The oracle runs:

1. **As an `auto_pre` node** (group 0) for specs in the initial task graph,
   alongside or sequentially with the skeptic (if both are enabled).
2. **At the sync barrier** when new specs are hot-loaded, injecting oracle
   nodes for each newly discovered spec before their first coder group executes.

The oracle produces structured **drift findings** categorized by severity. These
findings are:

- Stored in the DuckDB knowledge store (same pattern as skeptic findings).
- Injected into the coder's session context as warnings.
- Optionally **blocking** if the number of critical drifts exceeds a
  configurable threshold (similar to the skeptic's `block_threshold`).

The oracle is a single-instance archetype (no multi-instance convergence).
It has read-only access to the codebase via a read-only shell allowlist plus
fox tools (if enabled).

## Relationship to Existing Features

The oracle **complements** the existing stale-dependency validation (spec 21).
Stale-dependency validation is a static lint-time check that only validates
backtick-delimited identifiers in the dependency table's Relationship column
against upstream `design.md` files. The oracle is a runtime agent that validates
**all spec files** (requirements, design, test_spec, tasks) against **actual
source code** in the repository. They serve different purposes and can coexist.

The oracle is similar to the skeptic in architecture (auto_pre injection,
structured findings, DuckDB storage, context rendering) but different in
purpose: the skeptic reviews spec **quality** (ambiguities, contradictions,
missing edge cases), while the oracle checks spec **freshness** (whether
referenced artifacts still exist and behave as assumed).

## Configuration

```toml
[archetypes]
oracle = true

[archetypes.oracle_settings]
block_threshold = 3   # block if > 3 critical drift findings

[archetypes.models]
oracle = "STANDARD"

[archetypes.allowlists]
oracle = ["ls", "cat", "git", "grep", "find", "head", "tail", "wc"]
```

## Non-Functional Requirements

- The oracle MUST NOT modify any source code or spec files (read-only).
- The oracle SHOULD complete within a single session timeout (default 30 min).
- Oracle findings MUST be deterministically parseable (structured JSON).
- The oracle MUST NOT introduce additional LLM calls for convergence (single
  instance).

## Out of Scope

- Automatic spec rewriting or patching based on drift findings.
- Multi-instance oracle execution with convergence.
- Oracle validation of non-spec artifacts (e.g., config files, CI pipelines).
