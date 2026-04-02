# PRD: Quality Gate Hunt Category

## Problem

Night-shift's hunt scanner discovers maintenance debt (dead code, TODOs,
documentation drift, etc.) but has no visibility into whether the project's
quality gates are actually passing. A broken build, failing tests, or lint
errors are the most urgent issues in any codebase, yet night-shift cannot
detect them today.

The `agent-fox fix` command already has check detection and execution logic
(`agent_fox.fix.checks`) that auto-discovers quality checks from project
configuration files (pyproject.toml, package.json, Makefile, Cargo.toml).
This capability should be surfaced as a night-shift hunt category so the
daemon can create issues for failing quality gates.

## Solution

Add a new built-in hunt category called `quality_gate` that:

1. **Auto-discovers** quality checks from project configuration files by
   reusing `detect_checks()` from `agent_fox.fix.checks`.
2. **Executes** each detected check as a subprocess with a configurable
   timeout (default: 600 seconds).
3. **Sends failure output to AI** for root-cause analysis, producing a
   structured Finding with a meaningful title, description, and suggested
   fix for each failing check.
4. **Produces one Finding per failing check** (not per individual error
   within a check).
5. **Produces zero findings** when all checks pass (silent on success).
6. **Runs independently** of other categories -- no deduplication with
   `linter_debt` or any other category.

## Clarifications

- **AI analysis**: Failure output is sent to the AI backend for root-cause
  analysis rather than being mechanically converted. This produces richer,
  more actionable findings.
- **One Finding per check**: Even if pytest reports 15 failures, the
  category produces one Finding for "pytest" with the AI-summarized root
  cause. The full output is preserved in the `evidence` field.
- **Timeout**: Configurable via `quality_gate_timeout` in the night-shift
  config. Default is 600 seconds (10 minutes), longer than the fix
  command's 300s default because night-shift runs unattended.
- **No overlap avoidance**: The `quality_gate` and `linter_debt` categories
  may produce findings about the same underlying issue (e.g., ruff errors).
  This is acceptable; the finding consolidation layer will group them if
  they share a `group_key`.
- **Check discovery**: Reuses the existing `detect_checks()` function which
  inspects pyproject.toml, package.json, Makefile, and Cargo.toml for
  configured tools.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 61_night_shift | 4 | 2 | Uses BaseHuntCategory, HuntCategoryRegistry, and Finding from group 4 where the hunt category system was implemented |
