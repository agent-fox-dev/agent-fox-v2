## Project Context

You are an agent-fox session agent. The orchestrator has already injected all
relevant spec context, task prompts, and curated knowledge into your system
prompt. Work within the context provided.

## Understand Before You Code (MANDATORY)

Before making any changes, orient yourself:

1. **Read `.agent-fox/steering.md`** if it exists — project-level directives that
   apply to all agents and skills. Follow any instructions found there.
2. **Read relevant specs** in `.specs/` for the area you're working on.
3. **Read ADRs** in `docs/adr/` for architectural context.
4. **Explore the codebase:** `<main_package>/` is the main package, `<test_directory>/` has
   unit, property, and integration tests. Their location is language dependent.
5. **Check git state:** `git log --oneline -20`, `git status --short --branch`.
6. **Run `make check`** to confirm the baseline is green. If tests fail, fix
   them before starting new work.

**Important:** Read all documents and code in depth — don't skim.

**Important:** Only read files tracked by git. Skip anything matched by
`.gitignore`. When in doubt, run `git ls-files` to see what's tracked.

**DO NOT READ `docs/memory.md`.** Relevant knowledge has already been retrieved
and injected by the adaptive retrieval pipeline. Reading the file directly
wastes context window on unfiltered, task-irrelevant content.

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

## Git Workflow

- **Conventional commits:** `<type>: <description>` (e.g. `feat:`, `fix:`,
  `refactor:`, `docs:`, `test:`, `chore:`).
- **Commit discipline:** only commit files relevant to the current change.
- **Never add `Co-Authored-By` lines.** No AI attribution in commits — ever.
- Do not switch branches, rebase, or merge into develop — the orchestrator
  handles integration.
- Never push to remote. The orchestrator handles remote integration.

## Scope Discipline

- Focus on one coherent change per session.
- Do not include unrelated "while here" fixes.
- Priority: fix broken behavior before adding new behavior.

## Documentation

- **ADRs** live in `docs/adr/NN-imperative-verb-phrase.md`. To choose NN,
  list existing files, find the max numeric prefix, and use the next number
  zero-padded to two digits for consistency (three digits once past 99).
- **Errata** live in `docs/errata/NN_snake_case_topic.md` — for spec
  divergences. NN is the spec number the erratum relates to (e.g.
  `28_github_issue_rest_api.md` for spec 28). For project-wide errata not
  tied to a specific spec, omit the numeric prefix.
- **Other docs** live in `docs/{topic}.md`.
- When you add or change user-facing behavior, public APIs, configuration, or
  architecture, update the relevant documentation in the same session.
