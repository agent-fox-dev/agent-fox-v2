# Requirements Document: AI Fix Pipeline Wiring (Spec 109)

## Introduction

This document specifies the requirements for wiring the existing AI-powered
fix functions (`rewrite_criteria`, `generate_test_spec_entries`,
`fix_ai_criteria`, `fix_ai_test_spec_entries`) into the `lint-spec --ai --fix`
pipeline. All generator and fixer functions already exist and are tested; this
spec covers only the dispatch and integration logic in `agent_fox/spec/lint.py`.

## Glossary

| Term | Definition |
|------|------------|
| **AI fix pipeline** | The dispatch logic that routes `AI_FIXABLE_RULES` findings to the correct AI generator function and then to the corresponding file fixer. |
| **AI generator** | An async function that sends findings to an AI model and returns structured fix data: `rewrite_criteria()` or `generate_test_spec_entries()`. |
| **AI fixer** | A synchronous function that applies AI-generated data to spec files: `fix_ai_criteria()` or `fix_ai_test_spec_entries()`. |
| **Mechanical fix** | A deterministic, non-AI fixer dispatched by `apply_fixes()` for rules in `FIXABLE_RULES`. |
| **AI_FIXABLE_RULES** | The set `{"vague-criterion", "implementation-leak", "untraced-requirement"}` defined in `fixers/types.py`. |
| **Batch limit** | Maximum number of findings sent in a single AI generator call to control prompt size and cost. |
| **findings_map** | A dict mapping `criterion_id` to `rule` name, used by `fix_ai_criteria()` to record the correct rule on each `FixResult`. |
| **STANDARD tier** | The default model tier for AI analysis and fix calls, resolved via `resolve_model("STANDARD")`. |

## Requirements

### Requirement 1: AI Fix Activation

**User Story:** As a spec author running `lint-spec --ai --fix`, I want
AI-detected quality issues to be automatically fixed, so that I don't have
to manually interpret and apply AI suggestions.

#### Acceptance Criteria

1. [109-REQ-1.1] WHEN both `--ai` and `--fix` flags are active AND findings
   exist with rules in `AI_FIXABLE_RULES`, THE system SHALL invoke the AI fix
   pipeline and return all resulting `FixResult` objects as part of
   `LintResult.fix_results`.

2. [109-REQ-1.2] WHEN `--fix` is active without `--ai`, THE system SHALL NOT
   invoke the AI fix pipeline.

3. [109-REQ-1.3] WHEN `--ai` is active without `--fix`, THE system SHALL NOT
   invoke the AI fix pipeline.

#### Edge Cases

1. [109-REQ-1.E1] IF no findings match `AI_FIXABLE_RULES`, THEN THE system
   SHALL skip the AI fix pipeline and return an empty list of AI fix results.

---

### Requirement 2: Criteria Rewrite Dispatch

**User Story:** As a spec author, I want `vague-criterion` and
`implementation-leak` findings to be dispatched to the rewrite pipeline,
so that my criteria are automatically improved to EARS quality.

#### Acceptance Criteria

1. [109-REQ-2.1] WHEN findings with rule `vague-criterion` or
   `implementation-leak` exist for a spec, THE system SHALL call
   `rewrite_criteria()` with that spec's `requirements.md` content and the
   filtered findings, AND pass the returned rewrites dict to
   `fix_ai_criteria()` along with the `findings_map`.

2. [109-REQ-2.2] THE system SHALL build a `findings_map` mapping
   `criterion_id` to rule name by extracting criterion IDs from finding
   messages using the `_REQ_ID_IN_MESSAGE` regex, AND pass it to
   `fix_ai_criteria()` so each `FixResult` carries the correct rule.

3. [109-REQ-2.3] THE system SHALL batch criteria findings per spec into
   groups of at most `_MAX_REWRITE_BATCH` per `rewrite_criteria()` call.

#### Edge Cases

1. [109-REQ-2.E1] IF `rewrite_criteria()` raises an exception for a spec,
   THEN THE system SHALL log a warning and continue processing remaining
   specs without aborting the AI fix pipeline.

2. [109-REQ-2.E2] IF `rewrite_criteria()` returns an empty dict for a batch,
   THEN THE system SHALL skip `fix_ai_criteria()` for that batch.

---

### Requirement 3: Test Spec Generation Dispatch

**User Story:** As a spec author, I want `untraced-requirement` findings to
be dispatched to the test spec generation pipeline, so that missing test
entries are automatically created.

#### Acceptance Criteria

1. [109-REQ-3.1] WHEN findings with rule `untraced-requirement` exist for a
   spec, THE system SHALL extract requirement IDs from finding messages, call
   `generate_test_spec_entries()` with the spec's `requirements.md` content,
   `test_spec.md` content, and the extracted IDs, AND pass the returned
   entries dict to `fix_ai_test_spec_entries()`.

2. [109-REQ-3.2] THE system SHALL batch untraced requirement IDs per spec
   into groups of at most `_MAX_UNTRACED_BATCH` per
   `generate_test_spec_entries()` call.

3. [109-REQ-3.3] THE system SHALL use the STANDARD-tier model (resolved via
   `resolve_model("STANDARD")`) for both `rewrite_criteria()` and
   `generate_test_spec_entries()` calls.

#### Edge Cases

1. [109-REQ-3.E1] IF `generate_test_spec_entries()` raises an exception for
   a spec, THEN THE system SHALL log a warning and continue processing
   remaining specs.

2. [109-REQ-3.E2] IF `generate_test_spec_entries()` returns an empty dict
   for a batch, THEN THE system SHALL skip `fix_ai_test_spec_entries()` for
   that batch.

3. [109-REQ-3.E3] IF a spec has `requirements.md` but no `test_spec.md`,
   THEN THE system SHALL skip test spec generation for that spec.

---

### Requirement 4: Execution Order

**User Story:** As a system operator, I want AI fixes to execute in the
correct order, so that downstream operations read up-to-date file content.

#### Acceptance Criteria

1. [109-REQ-4.1] THE system SHALL execute criteria rewrites before test spec
   generation for each spec, so that test spec generation reads the
   post-rewrite `requirements.md` content.

2. [109-REQ-4.2] THE system SHALL execute all AI fixes (via
   `_apply_ai_fixes()`) before calling `apply_fixes()` for mechanical fixes.

---

### Requirement 5: Re-validation After AI Fixes

**User Story:** As a spec author, I want the system to re-validate after
AI fixes so I see the true remaining findings, but I don't want infinite
fix loops.

#### Acceptance Criteria

1. [109-REQ-5.1] WHEN AI fixes produce at least one `FixResult`, THE system
   SHALL re-validate all specs (static validation plus AI analysis if `--ai`
   is active) before computing the final exit code.

2. [109-REQ-5.2] THE system SHALL NOT invoke the AI fix pipeline during
   re-validation -- AI fixes are applied at most once per `lint-spec`
   invocation.

#### Edge Cases

1. [109-REQ-5.E1] IF re-validation after AI fixes still flags a criterion
   that was rewritten, THEN THE system SHALL report it as a remaining finding
   without attempting another rewrite.
