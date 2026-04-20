# PRD: Fix-Coder Archetype for Night-Shift

## Problem

The night-shift fix pipeline reuses the `coder` archetype, which loads the
`coding.md` template. This template is designed for spec-driven development
and contains instructions that cause failures in issue-driven fix sessions:

1. **Task-group workflow confusion.** `coding.md` instructs the agent to "choose
   exactly one task group from `.specs/{spec_name}/tasks.md`" and "update
   checkbox states." When interpolated with `spec_name="fix-issue-313"`, the
   agent creates `.specs/fix-issue-313/tasks.md` on disk, polluting the spec
   directory with ephemeral artifacts.

2. **Implementation avoidance.** The agent follows the task-group planning
   workflow (create tasks.md, check boxes) instead of directly implementing
   the fix. The reviewer then correctly reports "no implementation changes
   were made."

3. **Spec artifact leakage.** The committed `.specs/fix-issue-*/tasks.md` files
   get harvested into `develop`, creating orphaned spec directories (observed
   for issues #218, #269, #301, #313).

Issue #310 removed pipeline-level spec creation wiring, but did not address the
agent's template-driven behavior.

## Solution

Create a dedicated `fix_coder` archetype with its own `fix_coding.md` template.
The template shares the same quality expectations as `coding.md` (git workflow,
quality gates, conventional commits) but replaces all spec/task-group references
with issue-focused instructions.

### Design Principles

- **Shared infrastructure.** Session runner, worktree setup, harvest, and SDK
  parameter resolution are reused. Only the prompt template differs.
- **Copy and diverge.** `fix_coding.md` is a standalone template, not a
  composition of shared fragments. The two templates serve different workflows
  and will diverge over time.
- **SDK param inheritance.** `fix_coder` uses the same registry defaults as
  `coder` (STANDARD tier, 300 max_turns, adaptive thinking). Users can override
  via `archetypes.overrides.fix_coder` in config.
- **No session artifacts.** The fix pipeline does not consume
  `.session-summary.json` or `.session-learnings.md`, so the fix_coder template
  omits those instructions.
- **Commit format in template.** The `fix(#NNN, nightshift):` commit format
  instruction belongs in the template, not in Python code. The agent extracts
  the issue number from the task prompt (which always contains `Issue #NNN`).

## Scope

- New template: `agent_fox/_templates/prompts/fix_coding.md`
- New archetype entry: `fix_coder` in `ARCHETYPE_REGISTRY`
- Updated: `fix_pipeline.py` to use `archetype="fix_coder"`
- Removed: hardcoded commit format appended in `_build_coder_prompt()`

## Out of Scope

- Cleaning up orphaned `.specs/fix-issue-*` directories (separate task)
- Changes to the triage or fix_reviewer archetypes
- Changes to the spec-driven `coding.md` template

## Clarifications

1. **SDK params:** `fix_coder` inherits `coder` defaults from the registry.
   Config overrides use `archetypes.overrides.fix_coder`.
2. **Session artifacts:** `fix_coding.md` does not instruct the agent to create
   `.session-summary.json` or `.session-learnings.md`.
3. **Commit format:** Moved into the template; removed from Python code.
4. **Template strategy:** Copy and diverge (option a) — standalone template.
