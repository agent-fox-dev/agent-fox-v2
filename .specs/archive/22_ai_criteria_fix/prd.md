# PRD: AI-Powered Criteria Auto-Fix

## Overview

Extend `lint-spec --fix` to automatically rewrite problematic acceptance
criteria in `requirements.md` when combined with the `--ai` flag. Currently
`--ai` detects `vague-criterion` and `implementation-leak` issues and reports
them as hint-severity findings with prose suggestions. When `--fix` is also
present, the system should make a second AI call to produce exact replacement
text and apply it in-place, turning the diagnostic into an automated rewrite.

## Problem Statement

Today, `lint-spec --ai` identifies two categories of acceptance-criteria quality
issues:

1. **Vague criteria** — subjective language like "should be fast" or "easy to
   use" that cannot be objectively verified.
2. **Implementation-leaking criteria** — criteria that prescribe *how* the
   system should be built rather than *what* it should do.

These findings are reported as hints with a free-text `Suggestion` field, but
the suggestion is a prose explanation ("Be more specific about latency
bounds"), not a drop-in replacement. The user must manually interpret each
suggestion, compose EARS-formatted text, locate the criterion in
`requirements.md`, and replace it — a tedious, error-prone process that
discourages spec quality improvements.

Meanwhile, the `--fix` flag already handles three mechanical rules
(`coarse-dependency`, `missing-verification`, `stale-dependency`). Extending it
to cover AI-detected criteria issues is the natural next step.

## Goals

1. When `lint-spec --ai --fix` is run, automatically rewrite flagged acceptance
   criteria to eliminate vagueness and implementation leaks.
2. Produce EARS-formatted replacement text that preserves the original
   requirement ID and intent.
3. Batch all fixable criteria per spec into a single AI rewrite call to
   minimize cost and latency.
4. Integrate seamlessly with the existing fix pipeline — same summary output,
   same re-validation cycle.

## Non-Goals

- Interactive confirmation or diff preview (future enhancement).
- Fixing requirements that have no acceptance criteria at all (that is a
  structural issue, not a quality issue).
- Rewriting edge-case requirements (only acceptance criteria are in scope).

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 09_spec_validation | 4 | 2 | Uses `Finding` model, `validate_specs`, CLI command structure from group 4 |
| 20_plan_analysis | 4 | 2 | Uses `apply_fixes`, `FixResult`, `FIXABLE_RULES` from fixer module (group 4) |
| 21_dependency_interface_validation | 4 | 2 | Extends AI validator patterns (`_extract_json`, `create_async_anthropic_client`) from group 4 |

## Clarifications

1. **Rewrite mechanism:** A dedicated AI rewrite call produces exact
   replacement text, not a prose suggestion. The analysis pass identifies
   what to fix; a separate rewrite call produces the fix.
2. **Call batching:** All fixable findings for a single spec are sent in one
   rewrite request containing the full `requirements.md` content plus the
   list of flagged criteria and their issues. This minimizes API calls.
3. **Silent application:** Rewrites are applied without interactive
   confirmation, consistent with the existing `--fix` UX for mechanical rules.
4. **Idempotency:** The rewrite prompt instructs the AI to produce text that
   would pass its own analysis. If a re-run still flags something, it is
   treated as accepted — no infinite loops.
5. **EARS preservation:** The rewrite prompt explicitly requires EARS syntax
   (`SHALL`, `WHEN`, `WHILE`, `IF/THEN`, `WHERE`) and preservation of
   requirement IDs.
