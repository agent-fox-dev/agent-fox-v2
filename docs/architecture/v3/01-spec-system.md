# Chapter 01 — Spec System

## Purpose

The spec system is the contract between human intent and machine execution. It is the single point where human judgment — what to build, what matters, what the constraints are — enters the system. Everything downstream (planning, execution, review, knowledge) derives from specs.

v3 lowers the barrier to entry while preserving the structural guarantees that make specs machine-readable and traceable.

## The Five-Artifact Spec Package

Every spec is a complete package of five artifacts. This is unchanged from v2, and non-negotiable. The five artifacts form a closed traceability chain — requirements define what to build, design defines how to build it, test spec defines how to verify it, tasks define the execution order, and the PRD ties them together with intent and constraints.

- `prd.md` — What you want built and why. Contains the problem statement, success criteria, cross-spec dependencies, and any constraints the author considers important.
- `requirements.md` — Formal requirements using EARS syntax with unique identifiers. The Verifier archetype uses these for pass/fail assessment.
- `design.md` — Architectural decisions, file layout, interface contracts, technology choices. Agents receive this as context and the Reviewer (drift-review mode) detects divergence.
- `test_spec.md` — Test contracts: what to test, expected behaviors, edge cases. The Reviewer (audit-review mode) validates test coverage against these contracts.
- `tasks.md` — The ordered list of task groups and subtasks. Each group is a unit of work assigned to one agent session.

Writing all five artifacts is front-loaded effort that pays for itself in execution quality. The `af-spec` skill assists with generation: given a PRD or natural-language description, it produces a complete, validated spec package through a guided workflow. The human reviews and commits. The system never auto-commits a generated spec — the human approval gate is non-negotiable.

## Spec Discovery and Layout

Specs live in a `.specs/` directory at the project root. Each spec is a subdirectory using the **`NN_snake_case_name`** naming convention:

- **`NN`** is a zero-padded two-digit running number (01, 02, 03, …) indicating creation order.
- **`snake_case_name`** is a short, descriptive name for the feature or workstream (e.g., `auth_system`, `payment_flow`).
- To choose the next number: scan `.specs/` for existing folders whose names start with digits and an underscore, take the maximum numeric prefix, and increment. If none exist, start at `01`.
- After choosing a number, verify no existing folder uses the same prefix. If a collision is found, increment until unique and flag the collision to the user.

The numeric prefix establishes a stable ordering and provides the two-digit identifier used in requirement IDs (`[NN-REQ-N.M]`), test spec IDs (`TS-NN-N`), and cross-spec dependency references.

```
.specs/
  01_auth_system/         # complete — plannable
    prd.md
    requirements.md
    design.md
    test_spec.md
    tasks.md
  02_payment_flow/        # work-in-progress — excluded from planning
    prd.md
    tasks.md
```

The planner discovers specs by scanning direct children of `.specs/` for directories containing all five artifacts (`prd.md`, `requirements.md`, `design.md`, `test_spec.md`, `tasks.md`). All five are required — a spec without any one of them is not plannable. Directories missing any artifact are flagged as incomplete during validation and excluded from planning. Work-in-progress specs can coexist with runnable ones — they just won't be planned until complete.

Subdirectories of `.specs/` (such as `.specs/archive/`) are not scanned. This convention allows superseded specs to be archived without affecting planning.

## Task Groups and Subtasks

`tasks.md` is a structured markdown document. Each top-level numbered item is a **task group** — a unit of work that maps to one agent session. Subtasks within a group are guidance for the agent, not individually dispatched.

### Task Group Format

Task groups are top-level list items with a numeric prefix followed by a period:

```markdown
- [ ] 1. Write failing spec tests
  - [ ] 1.1 Set up test file structure
  - [ ] 1.2 Translate acceptance-criterion tests

- [ ] 2. Implement parser core [archetype: coder]
  - [ ] 2.1 Define Pydantic models
  - [ ] 2.2 Implement markdown parsing

- [ ] 3. Verify integration [archetype: verifier]
```

**Numbering rules:**
- Numbering starts at 1.
- Numbers must be sequential with no gaps (1, 2, 3 — not 1, 2, 5).
- The parser treats the first integer before the period as the group number.

**Subtask format:**
- Subtasks are indented list items using `N.M` notation (e.g., `2.1`, `2.2`).
- Subtasks are informational context for the agent. The parser does not assign individual completion state to subtasks — completion is tracked at the group level in `plan.json`.
- A verification subtask at the end of each group is conventional but not parser-enforced. By convention, the last subtask in a group uses the label `N.verify` (e.g., `2.verify` for group 2) and describes how to confirm the group's work is correct. The parser treats verification subtasks identically to any other subtask — the naming convention is for human readability only.

**Auto-fix behavior:** When task groups are renumbered (e.g., after inserting a group), auto-fix updates the group numbers, subtask prefixes, and cross-references in the dependency table. It does not update references in other spec artifacts (`test_spec.md`, `requirements.md`) — those must be updated manually or by re-running the af-spec skill.

Task groups carry metadata via **inline tags** — structured annotations that override defaults for that group.

### Tag Syntax

Tags appear at the end of the task group title line, enclosed in square brackets. Multiple tags are separated by whitespace.

```
3. Run drift review [archetype: reviewer] [model: standard]
4. Implement auth module
5. Verify test coverage [archetype: verifier]
```

**Format:** `[key: value]` — the key, a colon, a space, and the value. The parser uses the `[key: value]` pattern (colon-space separator) to distinguish tags from markdown link syntax (which uses `[text](url)`).

**Available tags:**

| Tag | Valid Values | Default | Effect |
|-----|-------------|---------|--------|
| `archetype` | `coder`, `reviewer`, `verifier`, `maintainer` | `coder` | Override the archetype for this group |
| `model` | `simple`, `standard`, `advanced` | adaptive routing | Force a specific model tier |

**Rules:**

- Tag names and values are case-insensitive (`[Archetype: Reviewer]` is valid).
- A tag key may appear at most once per group. Duplicate keys are a validation error.
- Invalid tag keys or values are caught during static validation and produce blocking errors.
- Tags on subtask lines are ignored — only group-level tags are parsed.

**Completion tracking:** v2 tracked completion state via markdown checkboxes in `tasks.md` (`- [ ]`, `- [x]`). This was readable but fragile — checkbox state in markdown is a presentation concern, not a reliable state machine. Agents editing tasks could corrupt checkbox syntax, and merging concurrent changes to checkbox state was error-prone.

v3 moves completion state out of `tasks.md` entirely. Task group completion is tracked in the plan state file (`.agent-fox/plan.json`), which the engine updates atomically after each session. `tasks.md` remains a static, human-authored document — the task definitions and their ordering — with no mutable state.

**Note on checkbox syntax:** The `af-spec` skill generates `tasks.md` with markdown checkboxes (`- [ ]`, `- [x]`) as a human-readability convenience. The spec parser ignores checkbox state — it strips checkboxes during parsing and treats them as visual noise. `plan.json` is the sole source of truth for completion. Agents do not update checkboxes in `tasks.md`.

This allows partial re-runs: the planner reads completion state from `plan.json`, skips completed groups, and dispatches only remaining work. If the user modifies `tasks.md` (adding or reordering groups), the engine detects the content hash mismatch and prompts for re-planning.

## Cross-Spec Dependencies

Dependencies between specs are declared in `prd.md` under a `## Dependencies` heading using a four-column table. A dependency states that work in one spec requires completion of work in another spec (or a specific task group within another spec) before it can proceed.

The planner resolves these into graph edges. Unresolvable references (spec doesn't exist, group number out of range) are caught during validation, not at execution time.

### Dependency Table Format

```markdown
## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 01_spec_parser | 3 | 1 | Imports parsed spec models from group 3 |
| 03_knowledge_store | 2 | 4 | Uses fact query API produced in group 2 |
```

Column definitions:

- **Spec** — The directory name of the upstream spec (e.g., `01_spec_parser`).
- **From Group** — The task group number in the upstream spec that produces the needed artifact. This is the earliest group whose output the current spec consumes.
- **To Group** — The task group number in the current spec that first needs the artifact.
- **Relationship** — What the dependency provides, including why the chosen From Group is the earliest sufficient one.

### Sentinel Values

A `From Group` of `0` is a sentinel meaning "upstream spec not yet planned." The validator flags sentinel `0` as a warning (unresolved dependency), not a blocking error. It must be resolved before execution — the planner rejects plans with unresolved sentinels.

### Dependency-Free Specs

If a spec has no cross-spec dependencies, the `## Dependencies` section is omitted from `prd.md`.

### Validation Rules

The parser validates that: (a) each spec name in the dependency table corresponds to an existing directory in `.specs/`, (b) each group number is within the range of task groups defined in the referenced spec's `tasks.md`, (c) no circular dependencies exist in the group-level dependency graph, and (d) each referenced spec is complete (all five artifacts present). Missing specs produce a warning during authoring (the upstream spec may not exist yet) and a blocking error during planning. Incomplete upstream specs (directory exists but missing artifacts) produce a blocking error (`DEP-005`) during planning — the planner will not schedule work that depends on unfinished upstream specifications.

**Mutual spec dependencies.** Two specs may legally depend on each other if the group-level edges form no cycle. For example: spec A group 4 depends on spec B group 3, while spec B group 5 depends on spec A group 2. This is acyclic at the group level — A's groups 1-2 run first, then B's groups 1-3, then A's groups 3-4, then B's groups 4-5. However, mutual spec dependencies increase coupling and make execution order harder to reason about. The validator emits `DEP-006` (warning) when it detects mutual spec-level references so authors can verify the coupling is intentional.

## Validation

Validation is the gatekeeper between authoring and planning. It runs automatically before planning and can be invoked standalone.

**Static validation** (no LLM, fast, deterministic):
- Structural checks: all five artifacts present, markdown parses correctly, task groups numbered sequentially starting at 1, inline tags use valid keys and values, dependency table parses correctly.
- Cross-reference checks: every requirement ID referenced in `test_spec.md` must exist in `requirements.md` (referential integrity). Every requirement ID in `requirements.md` must be referenced by at least one test case in `test_spec.md` (coverage completeness — produces a warning, not a blocking error, to support incremental authoring). Every spec name in the dependency table must correspond to an existing directory in `.specs/`. Every group number in the dependency table must be within the range defined in the referenced spec's `tasks.md`.
- Consistency checks: task group counts match between `tasks.md` and any references in other artifacts. Sentinel `0` in dependency `From Group` produces a warning.

**AI-assisted validation** (LLM, optional, deeper):
- Ambiguity detection: scan requirements for vague language ("should handle errors appropriately"), flag for human clarification.
- Completeness assessment: compare PRD success criteria against task list coverage. Identify gaps.
- Conflict detection: flag contradictions between PRD constraints and design decisions.

AI validation is advisory. It produces warnings, not blocking errors. The human decides whether to act on them.

**Validation output format:** Both static and AI-assisted validation produce findings in a uniform structured format: `{level: "error" | "warning", artifact: "<filename>", line: <number>, code: "<check-id>", message: "<description>"}`. Static findings are deterministic. AI findings include an additional `confidence` field. Error-level findings block planning. Warning-level findings are informational.

**Static check code registry:**

| Code | Level | Check |
|------|-------|-------|
| `SPEC-001` | error | Missing required artifact (one of the five) |
| `SPEC-002` | error | Markdown parsing failure |
| `TASK-001` | error | Task groups not numbered sequentially starting at 1 |
| `TASK-002` | error | Invalid inline tag key or value |
| `TASK-003` | error | Duplicate tag key on a single task group |
| `DEP-001` | error | Dependency references non-existent spec directory |
| `DEP-002` | error | Dependency references out-of-range group number |
| `DEP-003` | error | Circular dependency in the group-level graph |
| `DEP-004` | warning | Sentinel `From Group = 0` (unresolved dependency) |
| `DEP-005` | error | Dependency references incomplete spec (missing artifacts) |
| `DEP-006` | warning | Mutual spec-level dependency detected (spec A references spec B and vice versa) |
| `REQ-001` | error | Requirement ID in `test_spec.md` not found in `requirements.md` |
| `REQ-002` | warning | Requirement ID in `requirements.md` not referenced by any test in `test_spec.md` |
| `REQ-003` | error | Duplicate requirement ID within a spec |
| `CONSIST-001` | warning | Task group count mismatch between `tasks.md` and references in other artifacts |
| `TASK-004` | warning | Two independent task groups claim overlapping deliverable files (detected via `design.md` File Layout) |

AI-assisted validation uses codes prefixed with `AI-`: `AI-AMBIGUITY`, `AI-COVERAGE-GAP`, `AI-CONTRADICTION`. AI codes are advisory and always produce warnings, never errors.

**Requirement ID format:** Requirement IDs follow the pattern `[NN-REQ-N.M]` where `NN` is the spec's two-digit numeric prefix (e.g., spec `01_spec_parser` → `01`), `N` is the section number, and `M` is the requirement number within that section. Example: `[01-REQ-3.2]` is the second requirement in section 3 of spec 01. IDs must be unique within a spec. Cross-spec references retain the source spec's prefix (spec 02 referencing spec 01's requirement uses `[01-REQ-3.2]`).

**Auto-fix** applies mechanical corrections for common structural issues: renumbering task groups after insertion (including subtask prefixes and dependency table group numbers), adding missing requirement ID prefixes (e.g., `REQ-1.1` → `[05-REQ-1.1]` for a spec with prefix `05`), and normalizing tag syntax (case, whitespace). Auto-fix only adds prefixes within the current spec's `requirements.md` — it does not modify cross-spec references. Auto-fix never changes semantic content — it fixes formatting, not meaning.

## Spec Immutability During Execution

Once the planner has consumed a spec and produced a plan, the spec artifacts are treated as immutable for the duration of that plan's execution. Agents receive spec content as context but cannot modify spec files. This is a deliberate constraint: specs are the contract, and contracts don't change mid-execution.

**Enforcement:** In sandbox mode, the `.specs/` directory is mounted read-only in the container. In `--no-sandbox` mode, the system prompt instructs agents not to modify spec files, and the workspace package excludes `.specs/` from the agent's writable worktree paths. This is defense-in-depth — the sandbox enforces it mechanically, the prompt enforces it behaviorally.

If the user modifies a spec while execution is in progress, the changes are not picked up until the next planning cycle. The system does not attempt to detect or reconcile mid-execution spec changes — it would introduce non-determinism that undermines the planning guarantee.

**When cross-spec dependencies mismatch at runtime:** If an upstream spec's output doesn't match what a downstream spec expects — a different API than specified, different file locations, or incompatible data formats — the downstream Coder session will encounter errors and fail. This follows the standard failure path: assess as failure, retry with escalation, eventually mark as blocked (ch 03, Session Lifecycle). The blocked state surfaces in `af status`, and the human diagnoses the mismatch, modifies the affected spec(s), and re-plans. There is no automated detection of dependency contract mismatches before execution begins. The Relationship column in the dependency table (described above) is the primary defense — a precise description of what the upstream group produces and why the downstream group needs it makes mismatches visible during spec authoring and review.

## Spec Authoring Guidance

These guidelines apply whether specs are hand-authored or generated by the `af-spec` skill. They address weaknesses identified during spec review — areas where imprecise authoring degrades downstream system behavior.

### Use explicit file paths in design.md

When `design.md` describes file layout, name concrete paths ("Create `src/auth/middleware.py`"), not abstract references ("add an auth middleware module"). Explicit file paths feed two systems:

- **File impact prediction** (ch 03) — used to detect merge conflicts before they happen. Vague references produce empty impact sets, which means the engine can't prevent conflicting sessions from running concurrently.
- **Knowledge staleness** (ch 04) — facts track `source_files` for change-triggered decay. If the design doc doesn't name files, extracted facts won't have file associations and will rely on time-based decay alone.

When the File Layout lists files produced by the spec, annotate each entry with the producing task group number using a `[group N]` tag — e.g., "`src/auth/middleware.py` — [group 2] JWT validation middleware." Group annotations feed two additional systems:

- **Scope Guard pre-flight check** (ch 03 §Prepare) — determines which files belong to which group and whether a group's deliverables already exist. Without annotations, the pre-flight check cannot determine per-group deliverables and skips the check for that group.
- **TASK-004 validation** — detects when two independent task groups claim overlapping deliverable files.

### Write precise dependency contracts

The Relationship column in the dependency table is the primary defense against cross-spec mismatches at runtime (see Spec Immutability above). Name specific types, functions, or interfaces — not just the general relationship.

**Weak:** `Imports parsed spec models from group 3`

**Strong:** `Imports SpecPackage and TaskGroup types from agent_fox.spec.models, first defined in group 3`

Precise contracts allow the Reviewer (drift-review mode, with shell access) to verify that the upstream spec's output matches the downstream spec's expectations before any code is written.

### Flag mutual spec dependencies

Two specs may legally depend on each other at the group level (see Cross-Spec Dependencies above). But mutual dependencies increase coupling and make execution order harder to reason about. When declaring a dependency on a spec that already depends on the current spec, note the mutual relationship in the Relationship column and verify the group-level graph is acyclic. The validator emits `DEP-006` for these cases.

## Spec Generation Assistance

For users who find writing specs from scratch intimidating, the `af-spec` skill assists with generation. Given a natural-language description of what to build, the skill walks the user through a guided workflow that produces a complete five-artifact spec package. The human reviews, edits, and commits. The system never auto-commits a generated spec — the human approval gate is non-negotiable.

This is explicitly a convenience feature, not a core architectural component. The system works identically whether specs are hand-authored or machine-assisted.

---

*Previous: [00 — Overview](./00-overview.md)*
*Next: [02 — Architecture & Library Design](./02-architecture.md)*
