# Agent Instructions

Instructions for coding agents (Cursor, Claude Code, Codex, etc.) working on
this repository. Treat this file as mandatory policy for every coding session.

## Understand Before You Code (MANDATORY)

Before making any changes, orient yourself:

1. **Read `README.md`** for project overview and quick-start.
2. **Read `docs/memory.md`** — accumulated knowledge from prior automated
   sessions: gotchas, patterns, decisions, conventions, fragile areas. Skipping
   this file means repeating mistakes that were already discovered.
3. **Read relevant specs** in `.specs/` for the area you're working on.
4. **Read ADRs** in `docs/adr/` for architectural context.
5. **Explore the codebase:** `agent_fox/` is the main package, `tests/` has
   unit, property, and integration tests.
6. **Check git state:** `git log --oneline -20`, `git status --short --branch`.
7. **Run `make check`** to confirm the baseline is green. If tests fail, fix
   them before starting new work.

**Important:** Read all documents and code in depth — don't skim.

**Important:** Only read files tracked by git. Skip anything matched by
`.gitignore`. When in doubt, run `git ls-files` to see what's tracked.

Do not implement anything before completing these steps.

## Project Structure

```
agent_fox/              # Main Python package (Python 3.12+, managed with uv)
agent_fox/_templates/   # Agent prompt templates and bundled skills
.specs/                 # Specifications (NN_snake_case_name/)
tests/                  # unit/, property/, integration/ test directories
docs/                   # Documentation
  adr/                  # Architecture Decision Records
  errata/               # Spec divergence notes
  memory.md             # Accumulated knowledge from automated sessions
  cli-reference.md      # CLI documentation
  skills.md             # Skill documentation
skills/                 # Claude Code skill definitions (source)
```

## Spec-Driven Workflow

This project uses spec-driven development. Specifications live in
`.specs/NN_name/` (numbered by creation order) and contain five artifacts:

- `prd.md` — product requirements document (source of truth)
- `requirements.md` — EARS-syntax acceptance criteria
- `design.md` — architecture, interfaces, correctness properties
- `test_spec.md` — language-agnostic test contracts
- `tasks.md` — implementation plan with checkboxes

**Conventions:**
- Task group 1 writes failing tests from `test_spec.md`; subsequent groups
  implement code to make those tests pass.
- If implementation diverges from a spec, create errata in `docs/errata/` —
  never modify spec files directly.
- Use `/af-spec` to generate specs, `/af-spec-audit` to audit compliance.

## Quality Commands

| Command | What it does |
|---------|-------------|
| `make check` | Run lint + all tests (use before committing) |
| `make test` | Run all tests (`uv run pytest -q`) |
| `make test-unit` | Unit tests only |
| `make test-property` | Property tests only |
| `make test-integration` | Integration tests only |
| `make lint` | Check ruff lint + ruff format |
| `make format` | Auto-format code with ruff |

## Git Workflow

- **Branch from `develop`**, not `main`: `feature/<descriptive-name>`.
- **Never commit directly** to `main` or `develop`.
- **Conventional commits:** `<type>: <description>` (e.g. `feat:`, `fix:`,
  `refactor:`, `docs:`, `test:`, `chore:`). For non-trivial changes, add a
  commit body explaining *why*.
- **Commit discipline:** only commit files relevant to the current change.
  Keep commits focused and traceable.
- **Never add `Co-Authored-By` lines.** No AI attribution in commits — ever.
- **Transient files:** do not commit `.session-summary.json` or
  `.session-learnings.md` — these are orchestrator artifacts.
- **Landing:** push the feature branch to `origin` and confirm a clean working
  tree before ending the session.

## Available Skills

| Skill | Purpose |
|-------|---------|
| `/af-spec` | Generate specs from a PRD, description, or GitHub issue |
| `/af-fix` | Autonomous GitHub issue fixer |
| `/af-spec-audit` | Spec compliance audit |
| `/af-code-simplifier` | Code simplification and refactoring |
| `/af-adr` | Create Architecture Decision Records |
| `/af-reverse-engineer` | Reverse-engineer PRD from codebase |

## Scope Discipline

- Focus on one coherent change per session.
- Do not include unrelated "while here" fixes.
- If asked for multiple changes, complete one and hand off the rest.
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

1. `make check` passes (no regressions).
2. Changes are committed with a clear conventional commit message.
3. The feature branch is pushed to `origin`.
4. `git status` shows a clean working tree.
5. You provide a brief handoff note summarizing what was done and what remains.
