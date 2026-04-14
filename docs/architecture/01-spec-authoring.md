# Spec Authoring and Spec Structure

## Purpose and Placement

Specifications are the single source of truth that drives everything agent-fox
does. Every downstream activity — planning, coding, reviewing, verifying — traces
back to a spec. A spec is not documentation written after the fact; it is the
input artifact that the system consumes. If the spec is wrong, the code will be
wrong. If the spec is incomplete, the plan will have gaps. This is by design:
agent-fox treats specs as contracts, not suggestions.

This document covers how specs are structured, how the system discovers and
validates them, and how automated fixing keeps specs machine-readable without
requiring the author to memorize formatting rules. For how specs become
executable task graphs, see [Part 2: Planning](02-planning.md).

---

## The Spec as a Unit of Work

A specification maps to a single coherent feature, capability, or change. It
lives in a numbered directory under `.specs/` — for example,
`.specs/03_session_and_workspace/`. The numeric prefix establishes creation
order and provides a stable namespace for cross-spec references. The name after
the prefix is a snake_case descriptor chosen by the author.

Each spec directory contains exactly five artifacts:

| Artifact | Role |
|---|---|
| `prd.md` | Product requirements document. Defines what the feature is, why it exists, and what cross-spec dependencies it has. This is the human-facing narrative. |
| `requirements.md` | Acceptance criteria in EARS-syntax. Each criterion has a structured identifier and a testable "SHALL" statement. This is what the Verifier checks against. |
| `design.md` | Architecture and interface design. Describes components, data models, correctness properties, error handling strategy, and definition of done. |
| `test_spec.md` | Language-agnostic test contracts. Each entry describes what must be tested, not how. The Coder writes actual tests from these contracts; the Auditor verifies alignment. |
| `tasks.md` | Implementation plan as a dependency-ordered list of task groups with subtasks. This is what the planner parses into the task graph. |

These five artifacts form a closed traceability chain: requirements define what
must be true, test specs define how to verify it, tasks define how to build it,
design defines the shape of the solution, and the PRD provides the motivation.
The validation system enforces this chain — untraced requirements, orphaned test
entries, and missing coverage matrix rows are all flagged.

### Why Five Artifacts Instead of One

A single document would be simpler to author but harder to consume
programmatically. The planner only needs `tasks.md` and `prd.md`. The Coder
needs `requirements.md`, `design.md`, `test_spec.md`, and `tasks.md`. The
Verifier needs `requirements.md`. Splitting by concern means each consumer reads
only what it needs, and validation rules can target specific artifacts without
parsing a monolith.

The separation also enables independent evolution. A design change does not
require re-parsing the task list. A new requirement can be added to
`requirements.md` and traced through `test_spec.md` and `tasks.md` without
touching the PRD.

---

## Requirement Identifiers and Traceability

Every requirement carries a structured identifier of the form `NN-REQ-M.S`,
where `NN` is the spec's numeric prefix, `M` is the requirement number, and `S`
is the sub-requirement number. Error-handling requirements use the variant
`NN-REQ-M.EN`. These identifiers are the primary key for the traceability chain.

The chain works as follows:

1. `requirements.md` defines `NN-REQ-M.S` entries with acceptance criteria.
2. `test_spec.md` contains `TS-NN-N` entries that reference requirement IDs.
   Correctness properties in `design.md` are covered by `TS-NN-PN` entries.
3. `tasks.md` contains a traceability table mapping requirement IDs to task
   groups and test entries.
4. `test_spec.md` contains a coverage matrix mapping requirement IDs to test
   entries.

Validation enforces every link in this chain. An untraced requirement (present
in `requirements.md` but absent from `test_spec.md`) is flagged. An orphaned
test entry (present in `test_spec.md` but not referenced in `tasks.md`) is
flagged. A coverage matrix that omits a requirement is flagged. These are
warnings, not errors — the system distinguishes between structural problems that
prevent planning (errors) and quality gaps that should be addressed (warnings).

---

## Task Groups and the Tasks Artifact

`tasks.md` is the artifact the planner consumes directly. It defines an ordered
list of task groups, each represented as a checkbox line:

A task group has a numeric index, a title, a completion state (tracked via
checkbox), and zero or more subtasks. Groups execute sequentially within a spec
by default — group 2 depends on group 1. Cross-spec dependencies are declared
in `prd.md` and override this default ordering.

### Group 1 Convention

By convention, task group 1 writes failing tests from `test_spec.md` without
implementing any production code. Subsequent groups implement code to make those
tests pass. This test-first discipline is enforced by the Coder's prompt
template, not by the spec structure itself — the spec system is agnostic to
this convention.

### Optional Groups

A group can be marked optional with an asterisk prefix in its title. Optional
groups are included in normal plans but excluded in fast mode, where the planner
removes them and rewires their dependencies so predecessors connect directly to
successors.

### Archetype Tags

A task group can carry an archetype tag — for example, `[archetype: skeptic]` —
that overrides the default assignment of "coder" for that group. This is useful
when a group represents a review or validation step that should be handled by a
specific agent type. The tag is the highest-priority assignment mechanism,
overriding both the builder's defaults and the automatic injection rules.

### Verification Subtasks

Each group is expected to contain a verification subtask (conventionally
numbered `N.V`). This subtask signals to the Coder that it should run
the quality gate and confirm the group's work before marking it complete.
Missing verification subtasks are flagged during validation and can be
auto-fixed.

---

## Dependency Declarations

Cross-spec dependencies are declared in `prd.md` using a structured table. Two
table formats are supported:

The **standard format** declares spec-level dependencies: "this spec depends on
that spec." It uses sentinel group numbers that resolve to the first or last
group during graph construction. This format is simple but coarse — it forces
full serialization between specs.

The **group-level format** declares precise group-to-group dependencies: "group
3 of this spec depends on group 2 of that spec." This enables finer-grained
parallelism because only the specific dependent groups are sequenced, not entire
specs.

Validation encourages the group-level format. If a spec uses the standard
format, a warning is emitted recommending conversion to group-level
declarations, and an auto-fixer can perform the conversion mechanically.

### Dependency Identifiers

The group-level format includes a "Relationship" column where authors describe
what the dependency is about, often referencing specific identifiers (function
names, interfaces, data types) in backtick-quoted code spans. The AI validation
system extracts these identifiers and checks whether they actually exist in the
upstream spec's `design.md`. If an identifier is stale — renamed, removed, or
never present — a warning is emitted and the auto-fixer can substitute the
correct identifier.

---

## Spec Discovery

Discovery is the entry point for both planning and linting. The system scans
`.specs/` for subdirectories matching the `NN_name` pattern (numeric prefix,
underscore, descriptive name). Each matching directory becomes a `SpecInfo`
record carrying the spec's name, numeric prefix, path, and which of the five
core artifacts are present.

Discovery is deterministic: specs are sorted by numeric prefix, producing a
stable ordering across runs. An optional filter can restrict operations to a
single spec by name.

The system requires at least one discoverable spec. If the `.specs/` directory
is empty or contains no matching subdirectories, a hard error is raised. Specs
without a `tasks.md` file are discovered but cannot be planned — they may exist
as reference material or work-in-progress.

---

## Validation

Validation is a layered pipeline with two stages: static validation (fast,
deterministic, no LLM calls) and AI validation (slower, non-deterministic, uses
an LLM for semantic analysis).

### Static Validation

Static validation runs approximately twenty rules organized into phases:

**Structural checks** verify that all five core artifacts exist. Missing files
are errors — they prevent planning.

**Task structure checks** examine `tasks.md` for oversized groups (more than six
subtasks, a heuristic for scope creep), missing verification subtasks, invalid
or malformed archetype tags, and invalid checkbox states.

**Requirements checks** ensure acceptance criteria have structured identifiers
and contain the "SHALL" keyword mandated by EARS syntax. Inconsistent identifier
formats (mixing bracket and bold styles) are flagged as hints.

**Dependency checks** validate cross-spec references: do the referenced specs
exist? Do the referenced group numbers exist within those specs? Is the
dependency format coarse when it could be group-level? Are there circular
dependencies? Cycle detection uses depth-first search with three-color marking
to identify spec-level cycles.

**Completeness checks** verify that `design.md` contains correctness properties,
an error-handling table, and a definition of done. They also verify that
`test_spec.md` has a coverage matrix and `tasks.md` has a traceability table.

**Traceability checks** enforce the full chain: untraced requirements (in
`requirements.md` but not `test_spec.md`), untraced test entries (in
`test_spec.md` but not `tasks.md`), untraced correctness properties (in
`design.md` but not `test_spec.md`), and orphaned error-handling references
(error table entries pointing to nonexistent requirements). Additionally,
coverage matrix completeness and traceability table completeness are checked —
every requirement ID should appear in both tables.

**Section schema checks** verify that each artifact contains the expected
heading structure. Required headings produce warnings when missing; optional
headings produce hints.

### Severity Model

Findings have three severity levels:

- **Error**: Structural problems that prevent planning or execution. Missing
  core files, broken dependency references, circular dependencies. Any error
  causes the lint command to exit with a non-zero code.
- **Warning**: Quality gaps that should be addressed but do not block execution.
  Missing verification subtasks, untraced requirements, coarse dependencies.
- **Hint**: Stylistic or minor suggestions. Inconsistent formatting, missing
  optional sections.

### AI Validation

AI validation adds two semantic checks that static rules cannot perform:

**Acceptance criteria analysis** sends `requirements.md` to an LLM and asks it
to identify vague criteria (unmeasurable, ambiguous) and implementation leaks
(criteria that prescribe implementation rather than behavior). These are reported
as hints because they require human judgment to resolve.

**Stale dependency validation** extracts backtick-quoted identifiers from
cross-spec dependency relationships and asks an LLM to verify whether each
identifier exists in the upstream spec's `design.md`. This catches rename drift
— when a function or interface was renamed in the upstream spec but the
downstream dependency declaration still uses the old name.

AI validation is optional and disabled by default. It runs after static
validation and its findings are merged into the same results stream.

---

## Auto-Fixing

The fixer system can mechanically correct many validation findings. Fixable
rules fall into two categories:

**Structural fixers** add missing sections, tables, and subtasks. A missing
traceability table gets a skeleton populated with requirement IDs. A missing
coverage matrix gets a similar skeleton. Missing correctness properties,
error-handling tables, and definition-of-done sections get stub templates. Groups
without verification subtasks get one appended.

**Normalization fixers** correct formatting inconsistencies. Mixed requirement
ID formats are unified to bracket style. Invalid checkbox characters are reset.
Malformed archetype tags are normalized. Standard-format dependency tables are
converted to group-level format.

**Table completeness fixers** append missing rows to existing tables. If the
traceability table is present but lacks rows for some requirement IDs, the fixer
appends TODO rows for the missing entries.

**AI fixers** handle the three findings that require LLM assistance: rewriting
vague or leaky acceptance criteria, and generating test spec entries for untraced
requirements. These fixers call the LLM to produce replacement text and splice
it into the appropriate artifact.

After all fixes are applied, validation runs again to confirm the fixes resolved
the findings. This re-validation pass ensures fixers do not introduce new
problems.

The fix pipeline is idempotent by design. Running the fixer twice on the same
spec produces the same result as running it once. Fixers read the current file
state, compute the necessary change, and write back — they do not accumulate
state across invocations.

---

## The Lint Command

The `agent-fox lint-specs` command ties discovery, validation, and fixing into
a single workflow. It discovers specs, filters out fully-implemented ones
(all task groups marked complete) unless `--all` is specified, runs static
validation, optionally runs AI validation with `--ai`, and optionally applies
fixes with `--fix`.

The exit code reflects the worst finding: zero if no errors, non-zero if any
error-severity finding remains after fixing. This makes the lint command usable
as a CI gate — a spec with structural problems blocks the pipeline.

Fully-implemented specs are excluded from linting by default because their
specs have served their purpose and may contain stale references to code that
has since evolved. The `--all` flag overrides this for auditing purposes.

---

## Authoring Workflow

The typical authoring workflow is:

1. Create a numbered directory under `.specs/` with the five artifact files.
   The `/af-spec` skill can generate these from a PRD, a GitHub issue URL, or
   a plain-English description.
2. Run `agent-fox lint-specs` to validate. Fix errors manually or with
   `--fix`. Address warnings as appropriate.
3. Run `agent-fox lint-specs --ai` for semantic analysis if desired.
4. Run `agent-fox plan` to build the task graph (see
   [Part 2: Planning](02-planning.md)).

Specs are immutable once planning begins. If implementation reveals that a spec
is wrong, the convention is to create an erratum in `docs/errata/` rather than
modifying the spec directly. This preserves the spec as a historical record of
intent and makes divergences explicit.

---

*Next: [Planning — From Specs to Task Graphs](02-planning.md)*
