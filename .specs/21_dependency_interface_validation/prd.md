# PRD: Dependency Interface Validation

## Overview

Add an AI-powered lint rule that validates cross-spec dependency
declarations against the upstream spec's `design.md`. When a dependency
table's Relationship column references an interface, type, or function
(e.g., `Uses store.SnippetStore.Delete()`), the rule checks whether the
upstream spec's `design.md` actually defines that artifact. This catches
stale, misspelled, or incorrect dependency declarations that would
otherwise go undetected until a coding session fails. When run with
`--fix`, the rule can automatically apply AI-suggested corrections to
the prd.md Relationship text.

## Problem Statement

Each spec's `prd.md` dependency table includes a Relationship column that
describes *what* the spec uses from the upstream spec. These references are
free-text and currently unchecked. Common problems:

- **Stale references:** An upstream spec's design is refactored, renaming
  `store.SnippetStore` to `store.Store`, but downstream dependency tables
  still reference the old name.
- **Wrong group number:** A dependency claims it needs group 3's output,
  but the referenced interface is actually defined in group 2's design
  section.
- **Misspelled identifiers:** `config.Confg` instead of `config.Config`.
- **Phantom interfaces:** A dependency references an interface that was
  removed or never existed in the upstream spec.

The existing `broken-dependency` rule (spec 09) only checks that spec
names and group numbers exist. It does not validate the Relationship
column's semantic content.

## Goals

- Add a `stale-dependency` AI lint rule (gated behind `--ai`) that reads
  each dependency row's Relationship text and cross-references it against
  the upstream spec's `design.md`
- Extract code identifiers (backtick-delimited tokens) from Relationship
  text as the primary validation targets
- Use an AI model to determine whether each identifier is defined,
  described, or implied by the upstream design document
- Produce Warning-severity findings for references that the AI cannot find
  in the upstream design
- When run with `--fix --ai`, automatically apply AI-suggested corrections
  to stale identifiers in prd.md Relationship text
- Gracefully degrade when `design.md` is missing or AI is unavailable

## Non-Goals

- Validating references against actual source code -- this rule validates
  spec-to-spec consistency, not spec-to-code consistency (that is
  af-spec-audit's job)
- Modifying the dependency table format (that is spec 20's
  `coarse-dependency` fixer's job)
- Checking intra-spec references (e.g., a spec referencing its own
  design.md)
- Auto-fixing when the AI has no suggestion (only fixes with a concrete
  suggested replacement are applied)

## Key Decisions

- **AI-powered, not regex-only.** Code identifiers in Relationship text
  are varied (types, functions, methods, package paths). A regex approach
  would need to parse the upstream design.md's code blocks, type stubs,
  and prose -- which is fragile. An AI model can reason about whether
  `store.SnippetStore.Delete()` is defined in a design document that
  mentions `SnippetStore` with a `Delete` method.
- **Warning severity, not Error.** The AI's judgment may have false
  positives (the design describes the concept but uses different naming
  conventions, or the reference is to a standard library symbol). Warning
  gives visibility without blocking CI.
- **Backtick extraction as primary signal.** Relationship text uses
  backticks to delimit code identifiers (e.g., `Uses \`config.Config\` for
  settings`). Extracting backtick-delimited tokens focuses the AI on
  concrete identifiers rather than prose descriptions.
- **Per-dependency-row validation.** Each dependency row is validated
  independently against the upstream spec's design.md. This keeps prompts
  focused and results attributable to specific rows.
- **Batch by upstream spec.** When multiple dependency rows reference the
  same upstream spec, the upstream design.md is read once and all rows are
  validated in a single AI call to reduce latency and cost.
- **Fix uses AI suggestion directly.** When the AI response includes a
  `suggestion` field with a concrete replacement identifier, `--fix`
  replaces the original backtick token in the Relationship text. When no
  suggestion is provided, the finding is reported but not auto-fixed.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 09_spec_validation | 2 | 2 | Extends `validate_specs()` pipeline and uses `Finding`, `SEVERITY_WARNING` types |
| 09_spec_validation | 4 | 2 | Follows same AI validation pattern as `analyze_acceptance_criteria()` in `ai_validator.py` |
| 01_core_foundation | 1 | 1 | Uses `create_async_anthropic_client()` for AI model access |
| 20_plan_analysis | 4 | 3 | Extends `--fix` flag and `apply_fixes()` fixer framework from `spec/fixer.py` |
