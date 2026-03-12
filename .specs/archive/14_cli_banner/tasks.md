# Implementation Plan: CLI Banner Enhancement

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec enhances the CLI banner in two files: `agent_fox/ui/banner.py` and
`agent_fox/cli/app.py`. Task group 1 writes failing tests, task group 2
implements the banner changes, and task group 3 is a checkpoint.

## Test Commands

- Spec tests: `uv run pytest tests/unit/ui/test_banner.py tests/unit/cli/test_app.py tests/property/ui/test_banner_props.py -q`
- Unit tests: `uv run pytest tests/unit/ -q`
- Property tests: `uv run pytest tests/property/ -q`
- All tests: `uv run pytest tests/ -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create banner unit test file
    - Create `tests/unit/ui/test_banner.py`
    - Implement TS-14-1: fox art present in output
    - Implement TS-14-2: fox art styled with header role
    - Implement TS-14-3: version + model line format
    - Implement TS-14-4: working directory in output (monkeypatch `Path.cwd`)
    - Implement TS-14-7: version/model line styled with header role
    - Implement TS-14-8: cwd line styled with muted role
    - Use `Console(file=StringIO())` to capture Rich output
    - _Test Spec: TS-14-1, TS-14-2, TS-14-3, TS-14-4, TS-14-7, TS-14-8_

  - [x] 1.2 Create banner edge case tests
    - Add to `tests/unit/ui/test_banner.py`
    - Implement TS-14-E1: model resolution failure shows raw value
    - Implement TS-14-E2: `Path.cwd()` OSError shows `(unknown)`
    - _Test Spec: TS-14-E1, TS-14-E2_

  - [x] 1.3 Create CLI integration tests for banner
    - Add to `tests/unit/cli/test_app.py` (or a new section)
    - Implement TS-14-5: banner appears with subcommand invocation
    - Implement TS-14-6: `--quiet` suppresses banner
    - Implement TS-14-E3: `--version` skips banner
    - _Test Spec: TS-14-5, TS-14-6, TS-14-E3_

  - [x] 1.4 Create banner property tests
    - Create `tests/property/ui/test_banner_props.py`
    - Implement TS-14-P1: fox art always present
    - Implement TS-14-P2: version line always present for valid models
    - Implement TS-14-P3: model fallback never crashes (fuzz with Hypothesis)
    - Implement TS-14-P4: quiet produces no output
    - Implement TS-14-P5: cwd always present
    - _Test Spec: TS-14-P1, TS-14-P2, TS-14-P3, TS-14-P4, TS-14-P5_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Implement banner enhancement
  - [x] 2.1 Update `agent_fox/ui/banner.py`
    - Add `FOX_ART` constant with the canonical fox ASCII art
    - Add `_resolve_coding_model_display(model_config)` helper that returns
      the resolved model ID or the raw config value on failure
    - Update `render_banner()` signature to accept `model_config: ModelConfig`
      and `quiet: bool = False`
    - Implement: if `quiet`, return immediately
    - Render fox art lines with `theme.header()` (or `theme.print(..., role="header")`)
    - Render version + model line: `agent-fox v{__version__}  model: {model_display}`
      using `theme.header()`
    - Render cwd line using `theme.print(str(Path.cwd()), role="muted")` with
      OSError fallback to `(unknown)`
    - Remove the old playful/neutral message line
    - _Requirements: 14-REQ-1.1, 14-REQ-1.2, 14-REQ-2.1, 14-REQ-2.2, 14-REQ-2.3, 14-REQ-2.E1, 14-REQ-3.1, 14-REQ-3.2, 14-REQ-3.E1_

  - [x] 2.2 Update `agent_fox/cli/app.py`
    - Import `ModelConfig` (if not already imported)
    - Move banner rendering out of the `if ctx.invoked_subcommand is None` block
    - Call `render_banner(theme, config.models, quiet=quiet)` unconditionally
      (after config loading, before subcommand dispatch)
    - Keep the help text display inside the no-subcommand conditional
    - _Requirements: 14-REQ-4.1, 14-REQ-4.2_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest tests/unit/ui/test_banner.py tests/property/ui/test_banner_props.py -q`
    - [x] CLI integration tests pass: `uv run pytest tests/unit/cli/test_app.py -q`
    - [x] All existing tests still pass: `uv run pytest tests/ -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [x] Requirements 14-REQ-1.*, 14-REQ-2.*, 14-REQ-3.*, 14-REQ-4.* acceptance criteria met

- [x] 3. Checkpoint — CLI Banner Complete
  - Ensure all tests pass: `uv run pytest tests/ -q`
  - Ensure linter clean: `uv run ruff check agent_fox/ tests/`
  - Ask the user if questions arise.

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 14-REQ-1.1 | TS-14-1 | 2.1 | tests/unit/ui/test_banner.py |
| 14-REQ-1.2 | TS-14-2 | 2.1 | tests/unit/ui/test_banner.py |
| 14-REQ-2.1 | TS-14-3 | 2.1 | tests/unit/ui/test_banner.py |
| 14-REQ-2.2 | TS-14-3 | 2.1 | tests/unit/ui/test_banner.py |
| 14-REQ-2.3 | TS-14-7 | 2.1 | tests/unit/ui/test_banner.py |
| 14-REQ-2.E1 | TS-14-E1 | 2.1 | tests/unit/ui/test_banner.py |
| 14-REQ-3.1 | TS-14-4 | 2.1 | tests/unit/ui/test_banner.py |
| 14-REQ-3.2 | TS-14-8 | 2.1 | tests/unit/ui/test_banner.py |
| 14-REQ-3.E1 | TS-14-E2 | 2.1 | tests/unit/ui/test_banner.py |
| 14-REQ-4.1 | TS-14-5 | 2.2 | tests/unit/cli/test_app.py |
| 14-REQ-4.2 | TS-14-6 | 2.2 | tests/unit/cli/test_app.py |
| 14-REQ-4.E1 | TS-14-E3 | 2.2 | tests/unit/cli/test_app.py |
| Property 1 | TS-14-P1 | 2.1 | tests/property/ui/test_banner_props.py |
| Property 2 | TS-14-P2 | 2.1 | tests/property/ui/test_banner_props.py |
| Property 3 | TS-14-P3 | 2.1 | tests/property/ui/test_banner_props.py |
| Property 4 | TS-14-P4 | 2.1 | tests/property/ui/test_banner_props.py |
| Property 5 | TS-14-P5 | 2.1 | tests/property/ui/test_banner_props.py |

## Notes

- Use `Console(file=StringIO(), force_terminal=True)` in tests to capture
  Rich styled output including ANSI escape codes for role verification.
- Use `Console(file=StringIO())` without `force_terminal` when checking
  plain text content.
- The `render_banner` signature change is backward-incompatible — update all
  call sites (only `app.py`).
- Existing banner tests in `tests/unit/cli/test_app.py` may need updating
  since the banner now appears on all invocations.
