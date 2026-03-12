# Requirements Document: Dependency Interface Validation

## Introduction

This document specifies an AI-powered lint rule that validates cross-spec
dependency Relationship references against the upstream spec's `design.md`.
It extends the specification validation system (spec 09) with a new
`stale-dependency` rule gated behind the `--ai` flag, and adds an auto-fix
capability that applies AI-suggested corrections when run with `--fix --ai`.

## Glossary

| Term | Definition |
|------|-----------:|
| Relationship text | The free-text description in the Relationship column of a prd.md dependency table (e.g., "Uses `config.Config` for settings") |
| Code identifier | A backtick-delimited token within Relationship text representing a type, function, method, or package path (e.g., `config.Config`, `store.SnippetStore.Delete()`) |
| Upstream spec | The spec being depended on (the spec named in the Spec column of the dependency table) |
| Upstream design | The `design.md` file of the upstream spec |
| Stale reference | A code identifier in a Relationship that does not correspond to any interface, type, or function defined or described in the upstream design |

## Requirements

### Requirement 1: Identifier Extraction

**User Story:** As a spec validator, I need to extract code identifiers
from dependency Relationship text so I know what to validate against the
upstream design.

#### Acceptance Criteria

1. [21-REQ-1.1] THE system SHALL extract all backtick-delimited tokens
   from each dependency row's Relationship text as code identifiers.

2. [21-REQ-1.2] THE system SHALL strip trailing parentheses from extracted
   identifiers (e.g., `Delete()` becomes `Delete`) to normalize method
   references.

3. [21-REQ-1.3] THE system SHALL preserve dotted paths in identifiers
   (e.g., `store.SnippetStore.Delete` remains as-is) to support qualified
   name lookup.

#### Edge Cases

1. [21-REQ-1.E1] IF a Relationship cell contains no backtick-delimited
   tokens, THEN THE system SHALL skip that dependency row without
   producing a finding.

2. [21-REQ-1.E2] IF a backtick-delimited token is a common keyword or
   standard library reference (e.g., `slog`, `context.Context`, `error`),
   THE system SHALL still extract it but the AI validator is expected to
   recognize it as a standard symbol and not flag it.

---

### Requirement 2: Upstream Design Cross-Reference

**User Story:** As a spec author, I want stale dependency references caught
at lint time so I can fix them before a coding session discovers the
mismatch.

#### Acceptance Criteria

1. [21-REQ-2.1] WHERE the `--ai` flag is provided, THE lint-spec command
   SHALL include a `stale-dependency` validation rule that cross-references
   dependency Relationship identifiers against the upstream spec's
   `design.md`.

2. [21-REQ-2.2] FOR EACH upstream spec referenced by dependency rows, THE
   system SHALL read the upstream spec's `design.md` once and pass it along
   with the extracted identifiers to an AI model for validation.

3. [21-REQ-2.3] THE AI model SHALL determine whether each identifier is
   defined, described, or reasonably implied by the upstream design
   document.

4. [21-REQ-2.4] FOR EACH identifier that the AI determines is NOT present
   in the upstream design, THE system SHALL produce a Warning-severity
   finding identifying the declaring spec, the dependency row, the
   unresolved identifier, and the upstream spec.

5. [21-REQ-2.5] THE finding message SHALL include the AI's brief
   explanation of why the identifier was not found and, when possible, a
   suggested correction (e.g., "Did you mean `Store` instead of
   `SnippetStore`?").

#### Edge Cases

1. [21-REQ-2.E1] IF the upstream spec's `design.md` does not exist, THEN
   THE system SHALL skip validation for that upstream spec and produce no
   finding (the `missing-file` rule already covers missing files).

2. [21-REQ-2.E2] IF the AI model is unavailable (no credentials, network
   error, rate limit), THEN THE system SHALL log a warning, skip the
   `stale-dependency` rule entirely, and continue with other checks.

3. [21-REQ-2.E3] IF the AI response is malformed or unparseable, THEN THE
   system SHALL log a warning for that upstream spec and continue with the
   next one.

---

### Requirement 3: Batching and Efficiency

**User Story:** As a developer running lint-spec, I want validation to be
efficient so it does not take excessively long on projects with many specs.

#### Acceptance Criteria

1. [21-REQ-3.1] WHEN multiple dependency rows reference the same upstream
   spec, THE system SHALL batch them into a single AI call that validates
   all identifiers from those rows against the upstream design.md in one
   request.

2. [21-REQ-3.2] THE system SHALL read each upstream spec's `design.md` at
   most once, regardless of how many downstream specs reference it.

#### Edge Cases

1. [21-REQ-3.E1] IF a project has no cross-spec dependencies (no
   Relationship text across all specs), THEN THE system SHALL make zero
   AI calls for this rule.

---

### Requirement 4: Integration with Existing Validation

**User Story:** As a developer, I want the stale-dependency rule integrated
into the existing `--ai` flag so I do not need a separate command.

#### Acceptance Criteria

1. [21-REQ-4.1] THE `stale-dependency` rule SHALL run as part of the
   existing `--ai` validation pipeline in `lint-spec`, alongside the
   `vague-criterion` and `implementation-leak` rules.

2. [21-REQ-4.2] THE `stale-dependency` findings SHALL be sorted and
   displayed alongside all other findings using the existing output
   formatting (table, JSON, YAML).

3. [21-REQ-4.3] THE `stale-dependency` findings SHALL have severity
   `warning` and SHALL NOT cause a non-zero exit code on their own (only
   Error-severity findings cause exit code 1).

---

### Requirement 5: Auto-Fix for Stale Dependencies

**User Story:** As a spec author, I want `lint-spec --fix --ai` to
automatically correct stale identifiers in my dependency tables using the
AI's suggested replacements.

#### Acceptance Criteria

1. [21-REQ-5.1] WHEN `--fix` and `--ai` are both provided, THE system
   SHALL apply AI-suggested corrections for `stale-dependency` findings
   that include a concrete replacement identifier in the suggestion.

2. [21-REQ-5.2] THE fixer SHALL replace the original backtick-delimited
   identifier in the prd.md Relationship text with the AI-suggested
   identifier, preserving the surrounding text and backtick delimiters.

3. [21-REQ-5.3] THE fixer SHALL register `stale-dependency` in the
   `FIXABLE_RULES` set from `spec/fixer.py` so it integrates with the
   `--fix` framework from spec 20.

4. [21-REQ-5.4] THE fix summary SHALL include each corrected identifier
   and what it was changed to.

#### Edge Cases

1. [21-REQ-5.E1] IF the AI finding has no suggestion (suggestion is null
   or empty), THEN the fixer SHALL skip that finding and leave the
   identifier unchanged.

2. [21-REQ-5.E2] IF `--fix` is provided without `--ai`, THEN
   `stale-dependency` findings are not detected and therefore not fixed
   (the rule requires `--ai` to run).

3. [21-REQ-5.E3] IF the suggested identifier already exists in the
   Relationship text (the fix was already applied manually), THEN the
   fixer SHALL skip that finding to avoid duplicate text.
