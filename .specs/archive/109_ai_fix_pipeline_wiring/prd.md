# PRD: AI Fix Pipeline Wiring

## Background

Spec `22_ai_criteria_fix` (archived) implemented all the building blocks for
AI-powered spec auto-fix: the `rewrite_criteria()` async generator, the
`fix_ai_criteria()` file fixer, and the `rewrite_criteria.md` prompt template.
A parallel effort added the same pattern for test spec generation:
`generate_test_spec_entries()`, `fix_ai_test_spec_entries()`, and
`generate_test_spec.md`. The `AI_FIXABLE_RULES` constant in
`agent_fox/spec/fixers/types.py` already declares all three rules as
AI-fixable.

However, the integration point in `agent_fox/spec/lint.py` was never updated.
The `run_lint_specs()` function goes directly from AI analysis to mechanical
`apply_fixes()`, completely skipping the AI fix step. All AI fix code is dead
code in production.

## Problem Statement

When a user runs `lint-spec --ai --fix`, the system correctly detects
`vague-criterion`, `implementation-leak`, and `untraced-requirement` findings
via AI analysis. It then applies only mechanical fixes (like
`missing-verification` or `coarse-dependency`), ignoring the three AI-fixable
rules entirely. The user sees these findings flagged but never auto-fixed,
despite the fix infrastructure being fully implemented.

The missing piece is approximately 60-80 lines of wiring code in `lint.py`
that dispatches AI-fixable findings to the correct generator+fixer pair.

## Goals

1. Add an `_apply_ai_fixes()` helper function to `agent_fox/spec/lint.py`
   that dispatches AI findings to the correct generator+fixer pair.
2. Wire `_apply_ai_fixes()` into `run_lint_specs()` so it runs after AI
   analysis and before mechanical fixes.
3. Implement per-spec batching for both criteria rewrites and test spec
   generation, using configurable batch-limit constants.
4. Include AI fix results in the overall `LintResult.fix_results` list.
5. Re-validate after AI fixes exactly once (no re-fix loop).

## Non-Goals

- Modifying the existing `rewrite_criteria()`, `generate_test_spec_entries()`,
  `fix_ai_criteria()`, or `fix_ai_test_spec_entries()` implementations.
- Modifying the prompt templates (`rewrite_criteria.md`,
  `generate_test_spec.md`).
- Adding interactive confirmation or diff preview.
- Changing the `AI_FIXABLE_RULES` constant or the `Finding` model.

## Design Decisions

1. **Helper function pattern**: The new wiring logic lives in a dedicated
   `_apply_ai_fixes()` helper (with an `_apply_ai_fixes_async()` inner),
   following the same pattern as the existing `_merge_ai_findings()` helper.
   This keeps `run_lint_specs()` readable and the async boundary contained.

2. **Execution order**: AI fixes run before mechanical fixes because criteria
   rewrites modify `requirements.md`, which mechanical fixers
   (e.g., `missing-verification`) also touch. Within AI fixes, criteria
   rewrites run before test spec generation because rewrites change the
   `requirements.md` content that test spec generation reads for context.

3. **Re-validation policy**: After AI fixes, the system re-validates once
   (including AI analysis). If the same criterion is still flagged, it
   appears as a remaining finding -- no second rewrite attempt. This matches
   spec 22's stated policy (22-REQ-4.E1).

4. **Batch limit for test spec generation**: A `_MAX_UNTRACED_BATCH` constant
   (default 20) is defined in `lint.py` alongside `_MAX_REWRITE_BATCH`
   (also 20). Both are used by the wiring helper to split large finding sets
   into manageable AI call batches.

5. **Requirement ID extraction**: Untraced requirement IDs are extracted from
   finding messages using the existing `_REQ_ID_IN_MESSAGE` regex in
   `fixers/types.py`. This avoids breaking changes to the `Finding` model
   and is consistent with how `_extract_req_ids_from_findings()` in
   `fixers/runner.py` already works for mismatch findings.

6. **Model tier**: Both AI fix functions use the STANDARD tier via
   `resolve_model("STANDARD")`, matching the existing AI validation calls
   in `_merge_ai_findings()`.
