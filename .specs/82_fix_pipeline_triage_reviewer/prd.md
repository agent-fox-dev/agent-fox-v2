# PRD: Fix Pipeline Triage & Reviewer Archetypes

## Problem

The night-shift fix pipeline currently runs the `skeptic` and `verifier`
archetypes when processing `af:fix` GitHub issues. Both archetypes are
designed for spec-driven development: they expect formal specification
documents (requirements.md, design.md, test_spec.md, tasks.md) with
EARS-syntax acceptance criteria and structured requirement IDs.

Ad-hoc fix issues provide none of this. The issue body is free-form text
describing a bug or improvement. As a result:

- **Skeptic** receives a GitHub issue body where it expects spec documents. It
  cannot produce the required `{"findings": [...]}` JSON because there are no
  requirement IDs to reference and no spec structure to review. Output is
  consistently unparseable (`review.parse_failure` in audit logs).
- **Verifier** similarly expects requirement IDs and spec-based verdicts.
  Without them, it produces malformed output that the review parser discards.
- Both sessions burn ADVANCED-tier model calls with zero actionable output.

## Solution

Replace `skeptic` and `verifier` in the fix pipeline with two new
purpose-built archetypes:

1. **Triage** (replaces skeptic) -- Analyzes the issue, explores the affected
   codebase, and produces structured acceptance criteria formatted as test
   cases (following the `test_spec.md` convention). These criteria give the
   coder concrete targets and the reviewer concrete things to verify. Posts
   its report as a comment on the GitHub issue.

2. **Fix Reviewer** (replaces verifier) -- Verifies the coder's
   implementation against the triage-generated acceptance criteria. Runs the
   test suite, checks for regressions, and issues a PASS/FAIL verdict per
   criterion. Posts its report as a comment on the GitHub issue. On FAIL, the
   coder is retried with the reviewer's feedback injected, following the same
   retry and model-escalation workflow used in spec-based sessions.

## Scope

- The spec-based pipeline's skeptic and verifier remain unchanged.
- Only the fix pipeline (`FixPipeline.process_issue`) is affected.
- Both new archetypes are registered as first-class entries in the archetype
  registry.

## Clarifications

- **Triage output format**: Structured test cases following the `test_spec.md`
  document convention (ID, description, preconditions, expected, assertion).
- **Retry scope**: Only the coder retries on reviewer FAIL. Triage does not
  re-run.
- **Escalation config**: Reuses existing orchestrator config
  (`max_retries`, `retries_before_escalation`) -- no fix-pipeline-specific
  settings.
- **Prompt templates**: Dedicated `triage.md` and `fix_reviewer.md` in
  `_templates/prompts/`.
- **Archetype registry**: Both are first-class entries in `archetypes.py`.
- **Backward compatibility**: Spec-based pipeline unchanged.
