# Requirements: Fix Ruff Formatting Violations

## Requirement 1: Apply Ruff Formatting

All 43 Python files in the `agent_fox/` package that fail `ruff format --check` must be reformatted to comply with ruff's formatting rules.

**[FMT-REQ-1.1]** When `uv run ruff format --check agent_fox/` is executed, the system SHALL report zero files needing reformatting and exit with code 0.

**[FMT-REQ-1.2]** The formatting fix SHALL be applied by running `uv run ruff format agent_fox/`, which auto-formats all Python files in-place according to the project's ruff configuration.

**[FMT-REQ-1.3]** The formatting changes SHALL NOT alter program behavior, public APIs, or test outcomes of any module.

## Requirement 2: Preserve Existing Ruff Configuration

**[FMT-REQ-2.1]** The fix SHALL use the existing ruff configuration from `pyproject.toml` (or `ruff.toml` if present) without modification.

**[FMT-REQ-2.2]** No ruff configuration files SHALL be added, removed, or modified as part of this fix.

## Error Handling

**[FMT-REQ-1.E1]** If `uv run ruff format` fails to execute (e.g., ruff not installed, Python environment misconfigured), the error SHALL be reported and the fix SHALL not proceed.
