# Requirements Document: AI-Powered Criteria Auto-Fix (Spec 22)

## Introduction

This document specifies the requirements for extending the `lint-spec --fix`
command to automatically rewrite acceptance criteria flagged by AI analysis.
The feature adds a rewrite step to the existing lint-fix pipeline that
transforms vague or implementation-leaking criteria into EARS-formatted,
measurable acceptance criteria.

## Glossary

| Term | Definition |
|------|------------|
| **EARS** | Easy Approach to Requirements Syntax — a pattern language for writing unambiguous requirements using keywords like SHALL, WHEN, WHILE, IF/THEN, WHERE. |
| **Criterion** | A single numbered acceptance criterion within a requirement section of `requirements.md`. |
| **Requirement ID** | A globally unique identifier in the format `NN-REQ-N.C` (e.g., `09-REQ-1.1`). |
| **Vague criterion** | A criterion that uses subjective, unmeasurable language (rule: `vague-criterion`). |
| **Implementation leak** | A criterion that prescribes implementation details rather than observable behavior (rule: `implementation-leak`). |
| **Rewrite call** | A dedicated AI API call that produces exact replacement text for flagged criteria. |
| **Analysis finding** | A `Finding` object produced by the AI analysis pass, containing the criterion ID, issue type, and prose suggestion. |

## Requirements

### Requirement 1: AI Rewrite Integration

**User Story:** As a spec author, I want `lint-spec --ai --fix` to automatically rewrite problematic criteria, so that I don't have to manually interpret suggestions and compose replacements.

#### Acceptance Criteria

1. **22-REQ-1.1:** WHEN both `--ai` and `--fix` flags are provided AND the AI analysis produces findings with rule `vague-criterion` or `implementation-leak`, THE system SHALL invoke a rewrite step that produces exact replacement text for each flagged criterion.
2. **22-REQ-1.2:** WHEN the rewrite step produces replacement text, THE system SHALL write the modified `requirements.md` back to disk with the flagged criteria replaced in-place.
3. **22-REQ-1.3:** WHEN criteria are rewritten, THE system SHALL preserve the original requirement ID prefix (e.g., `**09-REQ-1.1:**` or `[09-REQ-1.1]`) in the rewritten text.
4. **22-REQ-1.4:** WHEN `--fix` is provided without `--ai`, THE system SHALL NOT invoke the AI rewrite step — only mechanical fixers run.

#### Edge Cases

1. **22-REQ-1.E1:** IF the AI rewrite call fails (network error, auth error, timeout), THEN THE system SHALL log a warning and skip the AI rewrite step, leaving the original criteria unchanged.
2. **22-REQ-1.E2:** IF a flagged criterion ID cannot be located in the `requirements.md` text, THEN THE system SHALL skip that criterion and log a warning.

---

### Requirement 2: Rewrite Prompt and EARS Compliance

**User Story:** As a spec author, I want rewritten criteria to follow EARS syntax and preserve the original intent, so that the automated fix produces spec-quality output.

#### Acceptance Criteria

1. **22-REQ-2.1:** THE rewrite prompt SHALL instruct the AI to use EARS syntax keywords (SHALL, WHEN, WHILE, IF/THEN, WHERE) in the replacement text.
2. **22-REQ-2.2:** THE rewrite prompt SHALL instruct the AI to preserve the original requirement's intent and behavioral scope — only fixing the identified quality issue (vagueness or implementation leak).
3. **22-REQ-2.3:** THE rewrite prompt SHALL instruct the AI to produce text that would pass the vague-criterion and implementation-leak analysis rules, preventing fix loops.
4. **22-REQ-2.4:** THE rewrite prompt SHALL include the full `requirements.md` content for context, plus the list of flagged criteria with their issue type and explanation.
5. **22-REQ-2.5:** THE AI response SHALL be a JSON object mapping each criterion ID to its replacement text.

#### Edge Cases

1. **22-REQ-2.E1:** IF the AI response is not valid JSON (including markdown-fenced JSON), THEN THE system SHALL attempt to extract JSON from code fences before failing.
2. **22-REQ-2.E2:** IF the AI response omits a requested criterion ID, THEN THE system SHALL skip that criterion without error.

---

### Requirement 3: Call Batching

**User Story:** As a system operator, I want AI rewrite calls to be batched per spec, so that API costs and latency are minimized.

#### Acceptance Criteria

1. **22-REQ-3.1:** THE system SHALL batch all fixable AI criteria findings for a single spec into one rewrite API call.
2. **22-REQ-3.2:** THE system SHALL NOT make a rewrite call for specs that have no fixable AI criteria findings.
3. **22-REQ-3.3:** THE system SHALL use the STANDARD-tier model (via the model registry) for rewrite calls.

#### Edge Cases

1. **22-REQ-3.E1:** IF a spec has more than 20 fixable criteria findings, THEN THE system SHALL split them into batches of at most 20 per rewrite call.

---

### Requirement 4: Fix Pipeline Integration

**User Story:** As a CLI user, I want AI rewrites to integrate with the existing fix summary and re-validation cycle, so that the output is consistent with mechanical fixes.

#### Acceptance Criteria

1. **22-REQ-4.1:** WHEN AI criteria rewrites are applied, THE system SHALL include them in the fix summary printed to stderr, using the format `N vague-criterion, M implementation-leak`.
2. **22-REQ-4.2:** WHEN AI criteria rewrites are applied, THE system SHALL re-validate the spec (including AI re-analysis) to produce the final findings list.
3. **22-REQ-4.3:** THE `FixResult` objects for AI rewrites SHALL use rule names `vague-criterion` or `implementation-leak` matching the original finding's rule.
4. **22-REQ-4.4:** THE `FIXABLE_RULES` set SHALL be extended to include `vague-criterion` and `implementation-leak` when AI mode is active.

#### Edge Cases

1. **22-REQ-4.E1:** IF re-validation after rewrite still flags the same criterion, THEN THE system SHALL report it as a remaining finding without attempting another rewrite.
