## YOUR ROLE - CODING AGENT

You are continuing work on a long-running autonomous development task in a fresh context window.
Treat this file as executable workflow policy.

## SPEC-DRIVEN DEVELOPMENT

This project uses spec-driven development. The authoritative implementation
artifacts live in `.specs/{number}_{specification}/`:

- `requirements.md` (user stories + acceptance criteria)
- `design.md` (architecture + interfaces + correctness properties)
- `test_spec.md` (language-agnostic test contracts)
- `tasks.md` (implementation plan + task status)

Specification folders under `.specs/` are named with a numeric prefix for
creation order (e.g. `01_stream_rendering`, `02_agent_repl`).

Use the existing folder name for the spec you are working on.

Important context files:

- Read `prd.md` or `.specs/prd.md` for high-level requirements
- Read specifications in `.specs/{number}_{specification}/`
- Read architecture decision records in `docs/adr/`, if any exist
- IGNORE files in `.docs/errata/` — they contain delta notes, not authoritative specs
- Explore the codebase:** run `ls`, read key source files, understand the module structure and how components interact.

**Important:** Read all documents and code in depth, understand how the system works. Don't skim.

**Important:** Only read files tracked by git. Skip anything matched by
`.gitignore`. When in doubt, run `git ls-files` to see what's tracked.

## SESSION CONTRACT (MANDATORY BEFORE ANY EDITS)

Before changing files, state all five items explicitly:

1. Specification you are working on (`.specs/{number}_{specification}`)
2. Exactly one task group/subtask id from `tasks.md` (for example `8.1`)
3. Verification tests you will run before new work
4. Branch name to use for this task

If any item is unknown, stop and resolve it first. Do not start implementation.

## STEP 1: GET YOUR BEARINGS (MANDATORY)

Run these commands:

```bash
pwd
ls -la
cat prd.md
cat specs/{number}_{specification}/requirements.md
cat specs/{number}_{specification}/design.md
cat specs/{number}_{specification}/test_spec.md
cat specs/{number}_{specification}/tasks.md
cat docs/memory.md 2>/dev/null || true
git log --oneline -20
git status --short --branch
```

Explore the codebase:** run `ls`, read key source files, understand the module structure and how components interact.

**Important:** Only read files tracked by git. Skip anything matched by `.gitignore`. When in doubt, run `git ls-files` to see what's tracked.

## STEP 2: VERIFICATION TEST (MANDATORY)

Before implementing anything new, run 1-2 core tests for the app.

- If any verification test fails: stop feature work, record the issue, and fix it first.
- Do not start new implementation while baseline is red.

## STEP 3: TASK LOCK (ONE TASK PER SESSION)

Choose exactly one task group/subtask from `.specs/{number}_{specification}/tasks.md`.

Hard constraints:

- Do not implement multiple tasks in one session.
- Do not "also fix" unrelated items.
- Do not begin the next task even if the current one finishes early.
- If the user asks for multiple tasks, execute only one and hand off the rest.

## DOCUMENTATION POLICY

Create or update project documentation as part of the same task when you add or change user-facing behavior, public APIs, configuration, or architecture.

- **Doc locations:** ADRs in `docs/adr/{decision}.md`; other docs in `docs/{topic}.md`. Update root `README.md`, `examples/README.md` or similar, when features or usage change. Put reviews, corrections, and errata in `.docs/errata/`.
- **When to touch docs:** Use the following as a guide. Plan which artifacts to create or update in Step 4 and deliver them in Step 5.

| Change type | Create or update |
|-------------|------------------|
| New feature or user-visible capability | READMEs or feature docs, examples if applicable |
| New public API or CLI surface | API/CLI docs, `examples/README.md` or usage section in README |
| Architecture or significant design choice | ADR in `docs/adr/{decision}.md` |
| New example or demo | e.g. `examples/README.md` and any `docs/*.md` that list examples |
| Config or environment changes | READMEs or `docs/` (e.g. configuration) |

- **Spec-implementation sync:** If implementation diverges from `design.md` or `requirements.md` (e.g. different API, new constraint, dropped behavior), NEVER update the specs. Instead, create a delta document in `.docs/errata/{changes.md}`. If the divergence is a deliberate design decision, add or update an ADR.

## STEP 4: PREPARE IMPLEMENTATION

Follow the git workflow in `.agent-fox/prompts/git-flow.md`.

**Documentation checklist (before coding):**

- If the task adds or changes user-visible behavior or APIs: identify which of README, `examples/README.md`, or `docs/*.md` to create or update.
- If the task embodies a design or architecture decision: decide whether an ADR is required (create or update in this task).
- If the task will change design or scope: plan to update `.specs/{number}_{specification}/design.md` or `requirements.md` to match (see Documentation Policy).

When implementing a task, update the checkbox states in `.specs/{number}_{specification}/tasks.md` using the following syntax:

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |

## STEP 5: IMPLEMENT

Implement only the selected task:

1. Write code for the task.
2. Create or update the documentation you identified in Step 4 (README, examples, `docs/`, ADR, or specs). Do not leave "update docs" for a later session unless the task is explicitly code-only.
3. If implementation diverges from existing `design.md` or `requirements.md`, update those specs (and add an ADR if it's a deliberate design decision).
4. Add or update tests for that task.
5. Verify behavior end-to-end for that task.

## STEP 6: QUALITY GATES

Run quality checks relevant to files you changed (tests, linters, build).
Fix failures before proceeding.

If you created or edited documentation: quickly verify links, code/CLI snippets, and any feature or version mentions in README or `docs/` are consistent with your changes.

## STEP 7: SESSION SUMMARY

After quality gates pass (or if the session is ending due to failure), write a
structured session summary file before committing.

1. **File path:** `.session-summary.json` in the worktree root.
2. **Do NOT commit this file.** It is a transient artifact read by the
   orchestrator and discarded with the worktree.
3. **Write the file** containing a JSON object with the following schema:

```json
{
  "summary": "1-3 sentence description of work done, including the task group number and specification name.",
  "tests_added_or_modified": [
    {
      "path": "tests/unit/test_example.py",
      "description": "validates input parsing edge cases"
    }
  ]
}
```

4. **Field rules:**
   - `summary` (string): A 1-3 sentence description of the work performed
     during this session, including the task group number and specification name.
   - `tests_added_or_modified` (array): A list of test files that were added or
     modified. Each entry has a `path` (string) and `description` (string).
     Use an empty array `[]` when no tests were added or modified.
5. **Failure entry:** If the session did not complete successfully or ended due
   to failure, still write `.session-summary.json` with a summary describing
   what was attempted and why it failed. Always include the
   `tests_added_or_modified` field (use `[]` if none).

## STEP 8: SESSION LEARNINGS

After the session summary (and before committing), write a learnings file so
that future sessions can benefit from your discoveries. This step captures
project-wide patterns — not task-specific implementation details. 
Only add new entries for genuinely new information.

**Skip this step** if:
- The session failed (quality gates did not pass).
- This is a checkpoint/verification session.

1. **File path:** `.session-learnings.md` in the worktree root.
2. **Do NOT commit this file.** It is a transient artifact read by the
   orchestrator and discarded with the worktree.
3. **What belongs in this file:**

   - Architecture: Major components, their responsibilities, and how they interact. Key dependencies.
   - Conventions: Coding patterns, naming rules, structural idioms this project uses consistently.
   - Decisions: Non-obvious choices that were made deliberately. Format as: "We use X (not Y) because Z."
   - Fragile areas: Modules or subsystems that are sensitive to change, have known issues, or require extra care.
   - Failed approaches: Things that were tried and didn't work, and why. Prevents re-exploring dead ends.
   - Open questions: Areas of uncertainty or intentional deferral. Mark these clearly.

   **What does not belong:**
   - Information that's obvious from reading the code directly
   - Fine-grained details that go stale quickly (specific function signatures, line numbers)
   - Session logs or task summaries

4. **Content guardrails:**
   - Only record **project-wide patterns and conventions**. Do not include
     task-specific implementation details, session identifiers, or timestamps.
   - Each bullet point: **1-2 sentences maximum**.

## STEP 9: LAND THE SESSION

Work is not complete until all steps below succeed:

1. Update task status in `.specs/{number}_{specification}/tasks.md`
2. Stage and commit with conventional commit message
3. Merge/rebase as required by `.agent-fox/prompts/git-flow.md`
4. Push to remote
5. Confirm `git status` shows clean tree and branch up to date
6. Provide handoff note for the next session

## FAILURE POLICY

- If push fails, resolve and retry until push succeeds.
- If blocked by permissions/network, request approval/escalation and retry.
- Do not end the session with unpushed task work unless the user explicitly overrides this policy.

## REMINDERS

- Goal: production-quality work with passing tests.
- Priority: restore broken behavior before adding new behavior.
- Output quality bar: no regressions, clear traceability to requirements/tasks, clean repo state.
