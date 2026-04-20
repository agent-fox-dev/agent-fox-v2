# PRD: Close lint-specs Coverage Gaps

## Problem

The `lint-specs` command validates specification files against structural and
quality rules defined by the `af-spec` skill. An audit revealed 6 checks
present in the af-spec completeness checklist (lines 974-1012 of the skill
definition) that have no corresponding validation rule in `lint-specs`.

This means specs can pass `lint-specs` while violating requirements that
`af-spec` explicitly mandates.

## Goal

Add 6 new validation rules to `lint-specs` so that every statically-checkable
item in the af-spec completeness checklist has a corresponding lint rule.

## New Rules

### 1. Missing Execution Paths section (design.md)

The af-spec skill requires a `## Execution Paths` section in `design.md` with
numbered call chains tracing every user-visible feature end-to-end.

**Rule:** `missing-execution-paths`
**Severity:** warning
**File:** design.md
**Check:** `## Execution Paths` section must exist.

### 2. Missing Integration Smoke Tests section (test_spec.md)

The af-spec skill requires a `## Integration Smoke Tests` section in
`test_spec.md` with one `TS-NN-SMOKE-N` entry per execution path.

**Rule:** `missing-smoke-tests-section`
**Severity:** warning
**File:** test_spec.md
**Check:** `## Integration Smoke Tests` section must exist.

### 3. Too many requirements (requirements.md)

The af-spec skill states a single spec SHOULD contain no more than 10
requirements (excluding edge cases).

**Rule:** `too-many-requirements`
**Severity:** warning
**File:** requirements.md
**Check:** Count `### Requirement N:` headings; warn if > 10.

### 4. Wrong first task group (tasks.md)

The af-spec skill mandates that task group 1 is always "Write failing spec
tests." This is non-negotiable.

**Rule:** `wrong-first-group`
**Severity:** warning
**File:** tasks.md
**Check:** First task group title must contain keywords "fail" and "test"
(case-insensitive substring match for resilience to phrasing variations).

### 5. Wrong last task group (tasks.md)

The af-spec skill mandates that the final task group is "Wiring verification."

**Rule:** `wrong-last-group`
**Severity:** warning
**File:** tasks.md
**Check:** Last task group title must contain keywords "wiring" and
"verification" (case-insensitive substring match).

### 6. Untraced edge case (test_spec.md)

The af-spec completeness checklist requires that every edge case requirement
(`NN-REQ-X.EN`) has a dedicated `TS-NN-EN` entry in the Edge Case Tests
section of `test_spec.md`.

The existing `untraced-requirement` rule checks that all req IDs appear
*somewhere* in test_spec.md, but does not enforce that edge case requirements
specifically appear within `TS-NN-EN` entries.

**Rule:** `untraced-edge-case`
**Severity:** warning
**File:** test_spec.md
**Check:** For each edge case req ID in requirements.md, verify it appears in
the `## Edge Case Tests` section of test_spec.md.

## Non-Goals

- AI/semantic validation rules (return value contracts, glossary cross-check,
  smoke test must-not-mock). These require LLM analysis and are out of scope.
- Content quality checks within sections (e.g., verifying call chain format
  in Execution Paths). Static presence checks are the minimum viable rules.

## Clarifications

1. **Title matching:** Use case-insensitive keyword/substring matching for
   task group titles (rules 4 and 5) to be resilient to minor phrasing
   variations by different agents.
2. **Edge case traceability:** This is a distinct check separate from
   `untraced-requirement` — it verifies edge case reqs appear in the
   Edge Case Tests section specifically, not just anywhere in test_spec.md.
3. **Severity:** All 6 rules use `warning` severity, consistent with existing
   structural checks.
4. **Completed spec exclusion:** Follows existing pattern — these rules are
   skipped for fully-implemented specs unless `--all` is passed.
5. **Backward compatibility:** Warning severity provides a natural grace
   period — findings are visible but do not cause a non-zero exit code (only
   `error` severity triggers exit code 1).
