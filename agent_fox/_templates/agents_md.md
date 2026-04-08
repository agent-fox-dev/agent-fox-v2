# Agent Instructions

Instructions for coding agents (Cursor, Claude Code, Codex, etc.) working on
this repository. Treat this file as mandatory policy for every coding session.

## Understand Before You Code (MANDATORY)

Before making any changes, orient yourself:

1. **Read `README.md`** for project overview and quick-start.
2. **Read `docs/memory.md`** — accumulated knowledge from prior automated
   sessions: gotchas, patterns, decisions, conventions, fragile areas. Skipping
   this file means repeating mistakes that were already discovered.
3. **Read `.specs/steering.md`** if it exists — project-level directives that
   apply to all agents and skills. Follow any instructions found there.
4. **Read relevant specs** in `.specs/` for the area you're working on.
5. **Read ADRs** in `docs/adr/` for architectural context.
6. **Explore the codebase:** `<main_package>/` is the main package, `<test_directory>/` has
   unit, property, and integration tests.
7. **Check git state:** `git log --oneline -20`, `git status --short --branch`.
8. **Run `make check`** to confirm the baseline is green. If tests fail, fix
   them before starting new work.

**Important:** Read all documents and code in depth — don't skim.

**Important:** Only read files tracked by git. Skip anything matched by
`.gitignore`. When in doubt, run `git ls-files` to see what's tracked.

Do not implement anything before completing these steps.

## Project Structure

```
<main_package>/         # Main package
<test_directory>/       # Tests directory
docs/                   # Documentation
.specs/                 # Specs to be implemented
.specs/archive/         # Old specs. Ignore for coding tasks, except for reference
```

## Spec-Driven Workflow

This project uses spec-driven development. Specifications live in
`.specs/NN_name/` (numbered by creation order) and contain five artifacts:

- `prd.md` — product requirements document (source of truth)
- `requirements.md` — EARS-syntax acceptance criteria
- `design.md` — architecture, interfaces, correctness properties
- `test_spec.md` — language-agnostic test contracts
- `tasks.md` — implementation plan with checkboxes

## Quality Commands

| Command | What it does |
|---------|-------------|
| `make check` | Run lint + all tests (use before committing) |
| `make test` | Run all tests (`uv run pytest -q`) |

Run the full quality suite before committing:

```
make check
```

## Git Workflow

- **Branch from `develop`**, not `main`: `feature/<descriptive-name>`.
- **Never commit directly** to `main` or `develop`.
- **Conventional commits:** `<type>: <description>` (e.g. `feat:`, `fix:`,
  `refactor:`, `docs:`, `test:`, `chore:`).
- **Commit discipline:** only commit files relevant to the current change.
- **Never add `Co-Authored-By` lines.** No AI attribution in commits — ever.
- **Feature branches are local-only** — do not push them to origin. Only
  `develop` (and `main` for releases) is pushed to the remote.

## Scope Discipline

- Focus on one coherent change per session.
- Do not include unrelated "while here" fixes.
- Priority: fix broken behavior before adding new behavior.

## Documentation

- **ADRs** live in `docs/adr/NN-imperative-verb-phrase.md`. To choose NN,
  list existing files, find the max numeric prefix, and use the next number
  zero-padded to two digits.
- **Errata** live in `docs/errata/NN_snake_case_topic.md` — for spec
  divergences. NN is the spec number the erratum relates to (e.g.
  `28_github_issue_rest_api.md` for spec 28). For project-wide errata not
  tied to a specific spec, omit the numeric prefix.
- **Other docs** live in `docs/{topic}.md`.
- When you add or change user-facing behavior, public APIs, configuration, or
  architecture, update the relevant documentation in the same session.

## Session Completion

A session is not complete until:

1. `make check` or `make test` passes (no regressions).
2. Changes are committed with a clear conventional commit message.
3. Changes are merged into `develop` locally.
4. `git status` shows a clean working tree.
5. You provide a brief handoff note summarizing what was done and what remains.