# PRD: Spec Lint Fixes

## Problem Statement

The `agent-fox lint-spec` command has three bugs that produce incorrect results:

### Bug 1: Subtask parser drops N.V verification steps

The subtask regex in `agent_fox/spec/parser.py` (`\d+\.\d+`) only matches
numeric subtask IDs like `1.1`, `2.3`. It does not match verification step
IDs like `1.V`, `2.V`. These subtasks are silently dropped during parsing.

**Impact:** The validator's `check_missing_verification` always reports
"missing verification step" for every group — even when the step exists in the
file — because the parser never delivers it.  The `check_oversized_groups`
count is also wrong (it never subtracts the verification step).

### Bug 2: False positives on completed specs

Completed specs (all task groups marked `[x]`) trigger warnings for
`oversized-group` and `missing-verification`. Once a spec is fully
implemented and merged, these structural convention warnings are noise.
Completed groups should be exempt from structural lint checks.

### Bug 3: Alternative dependency table format not validated

The `check_broken_dependencies` function only recognises the standard
dependency table header (`| This Spec | Depends On |`). The alternative
format with explicit group numbers (`| Spec | From Group | To Group |`) is
not validated at all. This is the format most specs actually use, and it's
where the `01_core_foundation:7` dangling reference went undetected.

### Skill Update

The `/af-spec` skill (`SKILL.md`) should include a validation step in the
dependency table instructions: after writing a dependency table, the skill
should verify that every referenced spec name exists in `.specs/` and every
referenced group number exists in that spec's `tasks.md`.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 09_spec_validation | 4 | 2 | Extends validator module and CLI from spec 09 |
