# Design: Fix Ruff Formatting Violations

## Approach

This is a mechanical, zero-risk fix. Ruff's formatter is deterministic and idempotent — running `uv run ruff format agent_fox/` will rewrite all 43 files to comply with the project's formatting rules in a single command.

## Architecture

No architectural changes are required. This fix modifies only whitespace, line breaks, trailing commas, quote styles, and other purely cosmetic formatting aspects as dictated by ruff's formatter.

## Execution Strategy

1. **Single command:** Run `uv run ruff format agent_fox/` to format all 43 files in-place.
2. **Verification:** Run `uv run ruff format --check agent_fox/` to confirm zero violations remain.

## Correctness Properties

### CP-1: Behavioral Equivalence
The formatted code must be semantically identical to the original. Ruff's formatter only modifies whitespace, line structure, and cosmetic elements — it does not change identifiers, logic, imports, or control flow.

### CP-2: Idempotency
Running `uv run ruff format agent_fox/` a second time must produce no further changes. This is guaranteed by ruff's formatter design.

### CP-3: Configuration Consistency
The formatter must respect the existing project ruff configuration (line length, quote style, etc.) from `pyproject.toml`. No configuration changes are made.

## Risk Assessment

- **Risk:** Extremely low. Ruff format is a well-tested, deterministic formatter.
- **Rollback:** `git checkout -- agent_fox/` reverts all changes instantly.
- **Side effects:** None. No runtime behavior changes.
