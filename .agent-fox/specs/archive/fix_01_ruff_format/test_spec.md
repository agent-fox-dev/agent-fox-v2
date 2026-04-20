# Test Specification: Fix Ruff Formatting Violations

## Test 1: Ruff Format Check Passes

**Contract:** After applying the fix, `uv run ruff format --check agent_fox/` must exit with code 0 and report no files needing reformatting.

```bash
uv run ruff format --check agent_fox/
# Expected: exit code 0, no "Would reformat" lines in output
```

**Verification:**
- Exit code is 0
- stdout/stderr contains no lines matching "Would reformat:"
- The output reports "X files already formatted" (or similar success message)

## Test 2: No Behavioral Changes

**Contract:** Existing tests must continue to pass after formatting changes.

```bash
uv run pytest
```

**Verification:**
- All existing tests pass with the same results as before the formatting fix.

## Test 3: Idempotency

**Contract:** Running the formatter again produces no changes.

```bash
uv run ruff format agent_fox/
uv run ruff format --check agent_fox/
# Expected: exit code 0 on the check (no further changes needed)
```

## Test 4: All 43 Files Addressed

**Contract:** Each of the 43 originally reported files must pass `ruff format --check` individually.

```bash
# Spot-check representative files from each module:
uv run ruff format --check agent_fox/cli/fix.py
uv run ruff format --check agent_fox/core/models.py
uv run ruff format --check agent_fox/engine/orchestrator.py
uv run ruff format --check agent_fox/fix/clusterer.py
uv run ruff format --check agent_fox/graph/types.py
uv run ruff format --check agent_fox/knowledge/causal.py
uv run ruff format --check agent_fox/memory/store.py
uv run ruff format --check agent_fox/reporting/formatters.py
uv run ruff format --check agent_fox/session/runner.py
uv run ruff format --check agent_fox/spec/validator.py
uv run ruff format --check agent_fox/ui/theme.py
uv run ruff format --check agent_fox/workspace/worktree.py
# Expected: all exit with code 0
```
