# PRD: Error Auto-Fix

**Source:** `.specs/prd.md` -- Section 5 "Error Auto-Fix" (REQ-070 through
REQ-074), Section 4 "Auto-Fix Failures" workflow, Section 7 "Fix Report" output
specification, Section 8 "No Quality Checks Found (Fix Command)".

## Overview

The error auto-fix system detects quality check failures (tests, lint,
type-check, build), groups them by root cause, generates fix specifications,
runs coding sessions to resolve them, and iterates until all checks pass or the
maximum number of passes is reached. It exposes this via the `agent-fox fix`
CLI command.

Unlike the standard `plan`/`code` workflow that requires hand-authored
specifications, the fix command generates specifications automatically from
detected failures. This makes it ideal for quick cleanup passes: broken tests,
lint violations, type errors, and build failures can be resolved without manual
triage or spec authoring.

## Problem Statement

Developers working with AI coding agents frequently encounter quality check
failures introduced during or between coding sessions: broken tests, lint
errors, type-check violations, and build failures. Currently, fixing these
requires the developer to manually triage failures, write fix specifications,
and run coding sessions. The fix command automates this entire cycle: detect
what is broken, figure out why, generate a plan, fix it, and verify.

## Goals

- Detect available quality checks by inspecting project configuration files
  (pyproject.toml, package.json, Makefile, Cargo.toml)
- Run detected checks, capture output, and parse failures into structured data
- Group failures by likely root cause using AI-assisted semantic analysis
- Generate fix specifications for each failure group
- Run coding sessions to resolve each group
- Iterate until all checks pass or max passes reached (default 3)
- Produce a summary report showing what was fixed and what remains
- Expose via `agent-fox fix` with `--max-passes` option

## Non-Goals

- Fixing failures that require external changes (dependency updates, API changes)
- Supporting custom or proprietary quality check tools beyond the detected set
- Replacing the standard spec-driven workflow for planned feature work
- Running fix sessions in parallel (sequential only for v1 of fix)
- Persisting fix specs permanently -- they are ephemeral, generated per run

## Key Decisions

- **Detection by file inspection.** The detector scans for known config files
  (pyproject.toml sections, package.json scripts, Makefile targets, Cargo.toml)
  to determine which checks are available. No user configuration required.
- **AI-assisted clustering with fallback.** Failure grouping uses the STANDARD
  model tier to semantically group related failures by root cause. If AI is
  unavailable, the system falls back to one group per check command.
- **Ephemeral fix specs.** Generated specs are written to
  `.agent-fox/fix_specs/` and cleaned up after the run. They use a minimal
  structure sufficient for the session runner.
- **Iterative convergence.** After each pass, checks are re-run. If new
  failures appear (e.g., fixing one test breaks another), they are grouped
  and addressed in the next pass.
- **Reuse of session machinery.** Fix sessions use the same SessionRunner and
  execution machinery as regular coding sessions (spec 03/04), ensuring
  consistent behavior, timeout enforcement, and security.

## Dependencies

| This Spec | Depends On | What It Uses |
|-----------|-----------|--------------|
| 08_error_autofix | 01_core_foundation | CLI framework (Click group, `main`), `AgentFoxConfig`, `AgentFoxError`, `AppTheme`, `resolve_model()`, logging |
| 08_error_autofix | 03_session_and_workspace | `SessionRunner` to execute fix coding sessions, `SessionOutcome` for results |
| 08_error_autofix | 04_orchestrator | Execution state management, cost tracking, session dispatch machinery |
