# Skills

agent-fox ships with a set of Claude Code skills -- slash commands that guide
you through common workflows like writing specs, documenting decisions, and
simplifying code. Skills are interactive: you invoke them in Claude Code and
work through the steps together with the agent.

## Quick Reference

| Skill | Command | Purpose |
|-------|---------|---------|
| [Spec Writer](#af-spec) | `/af-spec` | Transform a PRD or idea into a complete spec package |
| [Autonomous Fixer](#af-fix) | `/af-fix` | Analyze a GitHub issue, implement the fix, and land it |
| [Spec Audit](#af-spec-audit) | `/af-spec-audit` | Detect drift between specs and code |
| [Code Simplifier](#af-code-simplifier) | `/af-code-simplifier` | Analyze and simplify existing code |
| [ADR Writer](#af-adr) | `/af-adr` | Create Architecture Decision Records |
| [Reverse-Engineer PRD](#af-reverse-engineer) | `/af-reverse-engineer` | Generate a PRD from an existing codebase |

---

## af-spec

**Spec-driven development: from idea to implementation-ready spec package.**

Transforms a PRD, product idea, or GitHub issue into four specification
artifacts with full traceability from requirements through design, tests, and
tasks.

### What it produces

| File | Content |
|------|---------|
| `prd.md` | Finalized product requirements document |
| `requirements.md` | EARS-patterned acceptance criteria and edge cases |
| `design.md` | Interfaces, data models, correctness properties, error handling |
| `test_spec.md` | Language-agnostic test contracts with full requirement coverage |
| `tasks.md` | Implementation checklist (test-first: group 1 is always "write failing tests") |

All files are saved to `.specs/NN_specification_name/`.

### Workflow

1. **Understand the PRD** -- accepts a file path, GitHub issue URL, or inline
   description. Identifies ambiguities and asks for clarification.
2. **Learn the context** -- analyzes the existing codebase, finds the next spec
   number, identifies cross-spec dependencies.
3. **Write requirements** -- EARS syntax (WHEN/SHALL/IF/THEN), max 10
   requirements per spec, automated verification only.
4. **Write design** -- architecture overview with Mermaid diagrams, typed
   interfaces, correctness properties (formal invariants testable via
   property-based tests), error handling table.
5. **Write test spec** -- translates every acceptance criterion and correctness
   property into test contracts with preconditions, inputs, expected outputs,
   and assertion pseudocode. 100% coverage matrix.
6. **Write tasks** -- group 1 is always "write failing spec tests." Subsequent
   groups implement code. Each group has a verification subtask with specific
   test commands.

### When to use

Starting a new feature from a PRD, idea, or GitHub issue. When you want
test-first, spec-driven development with full traceability.

---

## af-fix

**Autonomous code fixer: from GitHub issue to landed fix.**

Takes a GitHub issue URL, deeply analyzes the problem, implements the fix, and
lands it on `develop` -- all in a single pass with minimal user interaction.

### Workflow

1. **Parse and fetch** -- validates the issue URL, fetches issue context
   (title, body, comments, linked PRs) via `gh`.
2. **Understand the codebase** -- reads docs, explores structure, runs existing
   tests to establish a baseline.
3. **Deep analysis** -- classifies the issue (bug, feature, refactor),
   performs root cause analysis for bugs, designs minimal solution for
   features. Posts an analysis comment to the issue.
4. **Implement** -- test-first: writes a regression test that fails, then the
   minimal fix. Runs all quality checks.
5. **Land** -- commits with conventional message (`fixes #N`), pushes feature
   branch, creates PR via `gh pr create`, merges into `develop`.

### When to use

When you have a GitHub issue and want it analyzed, fixed, tested, and landed
autonomously.

---

## af-spec-audit

**Spec compliance audit and drift detection.**

Compares what the specifications say should be built against what was actually
built. Produces a structured compliance report with actionable mitigations.

### What it produces

A report at `docs/audits/audit-report-{YYYY-MM-DD}.md` with:
- Summary table (compliant, drifted, unimplemented, superseded counts)
- Per-requirement classification with drift details
- Mitigation suggestions (change spec / get well spec / needs manual review)
- Priority assignments (high / medium / low)
- In-progress caveats (distinguishes expected gaps from real drift)
- Extra behavior detection (code not covered by any spec)

### Workflow

1. **Discover specs** -- scans `.specs/` for `NN_name` folders, reads all spec
   files in order.
2. **Build supersession chain** -- checks for explicit (`## Supersedes`) and
   implicit supersession between specs.
3. **Analyze the codebase** -- reads source code in depth, compares function
   signatures, data models, and error handling against design docs.
4. **Classify requirements** -- compliant, drifted (behavioral / structural /
   missing-edge-case), unimplemented, or superseded.
5. **Handle in-progress specs** -- uses `tasks.md` checkbox state to
   distinguish expected gaps from drift.
6. **Suggest mitigations** -- one per drift item, with priority.
7. **Generate report** -- saves to `docs/audits/audit-report-{YYYY-MM-DD}.md`.

### When to use

Verifying spec compliance after implementation sessions. Auditing completeness
before a review milestone or release. Detecting spec drift over time.

---

## af-code-simplifier

**Architecture and code-level simplification.**

Acts as a senior architect focused on making codebases smaller, clearer, and
easier to maintain. Analyzes at both architecture and code level, with a bias
toward removing code and collapsing unnecessary abstractions.

### Workflow

1. **Identify target** -- accepts a file, directory, or entire codebase.
2. **Structural analysis** -- maps dependency graph, detects over-engineering
   (single-implementation interfaces, pass-through wrappers, YAGNI
   abstractions), identifies consolidation candidates and dead weight.
3. **Code-level analysis** -- finds redundancy (DRY violations), readability
   issues (complex conditionals, deep nesting), outdated patterns, and
   structural smells (god classes, feature envy).
4. **Propose plan** -- three tiers: quick wins (dead code, naming), structural
   (file consolidation, inlining), design-level (pattern application, module
   reorganization). Waits for approval on tiers 2-3.
5. **Refactor** -- applies agreed changes with guard clauses, lookup tables,
   composition, modern idioms.
6. **Present changes** -- before/after comparison, LOC delta, file count delta.

### Priority hierarchy

1. Maintainability (always wins)
2. Readability
3. Reduced complexity
4. Fewer files/lines (signal, not goal)

### When to use

When code needs simplification, deduplication, structural improvement, or
complexity reduction. When you say "clean up", "simplify", or "refactor."

---

## af-adr

**Architecture Decision Records.**

Guides creation of ADRs that capture the context, alternatives, rationale, and
consequences of architectural decisions.

### What it produces

A markdown file at `docs/adr/NN-imperative-verb-phrase.md` with sections:

- **Context** -- the situation and forces (not the decision itself)
- **Decision Drivers** -- key requirements and constraints
- **Options Considered** -- at least two, each with honest pros and cons
- **Decision** -- chosen option with rationale tied to drivers
- **Consequences** -- positive, negative/trade-offs, and follow-up actions
- **References** -- RFCs, spikes, external docs

### Workflow

1. **Gather context** -- collects the decision, problem, alternatives, reasons,
   trade-offs, stakeholders, and status. Explores the codebase to verify
   claims.
2. **Determine location** -- finds existing ADR directory or creates
   `docs/adr/`. Determines next sequential number.
3. **Write the ADR** -- structured template with all sections.
4. **Quality check** -- validates: context explains WHY, at least two
   alternatives, rationale connects to drivers, consequences include negatives,
   no vague language.

### When to use

Making or documenting an architectural decision (technology choice, design
pattern, infrastructure change, build vs. buy).

---

## af-reverse-engineer

**Reverse-engineer a PRD from an existing codebase.**

Reads the codebase and produces a user-facing Product Requirements Document
describing what the product does -- never how it is implemented. The prime
directive is "WHAT, never HOW."

### What it produces

A `prd.md` with sections:

- Product Overview, Goals & Non-Goals
- User Personas (2-4 max)
- User Workflows (end-to-end journeys)
- Functional Requirements (EARS syntax)
- Configuration & Input Specification
- Output Specification
- Error Handling & User Feedback
- Constraints & Assumptions
- Open Questions

### Workflow

1. **Orient** -- reads entry points, public interfaces, configuration surface,
   and tests (for intent, not mechanics). Treats code as the source of truth.
2. **Translate** -- converts every code observation into a user-facing
   statement. No class names, function names, or implementation details.
3. **Write the PRD** -- 11 sections, all in user/product language.
4. **Quality checks** -- stakeholder test (could you present this to a VP?),
   implementation leak test (no code terms), testability test (can QA write
   tests from this?).

### When to use

When you have an existing codebase with no (or outdated) product documentation
and need a user-facing PRD. When onboarding new stakeholders.
