# PRD: CLI Separation and Logging Improvements

## Problem Statement

The agent-fox CLI has three categories of issues:

1. **Naming inconsistencies**: The `dump` command should be `export` (clearer
   intent), and `lint-spec` should be `lint-specs` (plural, matching the fact
   that it lints multiple specs).

2. **Poor CLI/module separation**: Several commands embed business logic
   directly in the Click handler, making it impossible to use the same
   functionality from code (e.g., importing and calling `run_lint_specs()` with
   the same options the CLI exposes). All 9 commands need audit and, where
   necessary, refactoring so that every `--option` maps to a parameter on a
   backing function that can be called without the CLI.

3. **Insufficient logging during `code` execution**: The current progress
   display lacks important operational context:
   - Tool argument truncation at 30 characters makes it hard to see what files
     are being read/edited.
   - No visibility into which archetype instances (Verifier, Oracle, Skeptic)
     are running or what they concluded.
   - No visibility when a reviewer disagrees and sends code back for retry.
   - No visibility when the system escalates to a more powerful model.

## Scope

### In scope

- Rename `dump` → `export` (identical flags: `--memory`, `--db`).
- Rename `lint-spec` → `lint-specs` (identical flags: `--ai`, `--fix`, `--all`).
- Remove old command names entirely (breaking change — no aliases).
- Extract backing modules for all 9 CLI commands so each command's full
  functionality is callable from Python code with explicit typed parameters.
- Increase tool-argument display truncation from 30 → 60 characters.
- Add archetype labels to task event lines (e.g., `✓ spec:1 [coder] done`).
- Add permanent status lines for: reviewer disagreements, retry events, and
  model escalation events.

### Out of scope

- Changing command option names or semantics beyond the renames.
- Adding new CLI commands.
- Changing the JSON output format.
- Modifying the audit event system.

## Clarifications

1. **Backward compatibility**: Old command names (`dump`, `lint-spec`) are
   removed entirely. No hidden aliases or deprecation period.
2. **API style**: Extracted backing functions use explicit typed parameters
   (not config objects). E.g., `run_lint_specs(ai=True, fix=True, lint_all=False)`.
3. **All 9 commands**: Every command gets audited for separation, even those
   that already have decent separation, to ensure consistency.
4. **Display style**: Archetype labels are included in permanent task lines,
   with additional lines for retry/escalation/disagreement events (preview
   format confirmed by user).
5. **Truncation limit**: Tool argument display increases from 30 to 60 characters.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 58_predecessor_escalation | 2 | 1 | Uses escalation ladder types in test assertions; group 2 is where escalation logic is implemented |
