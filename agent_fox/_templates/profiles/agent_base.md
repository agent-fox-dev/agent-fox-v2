## Project Context

You are an agent-fox session agent. The orchestrator has already injected all
relevant spec context, task prompts, and curated knowledge into your system
prompt. Work within the context provided.

**Do NOT read `docs/memory.md`.** Relevant knowledge has already been retrieved
and injected by the adaptive retrieval pipeline. Reading the file directly
wastes context window on unfiltered, task-irrelevant content.

## Project Structure

```
agent_fox/              # Main package
tests/                  # Tests (unit, property, integration)
docs/                   # Documentation
.specs/                 # Specifications
.specs/archive/         # Archived specs (reference only)
```

## Spec-Driven Workflow

Specifications live in `.specs/NN_name/` and contain:

- `prd.md` -- product requirements document (source of truth)
- `requirements.md` -- EARS-syntax acceptance criteria
- `design.md` -- architecture, interfaces, correctness properties
- `test_spec.md` -- language-agnostic test contracts
- `tasks.md` -- implementation plan with checkboxes

## Quality Commands

| Command | What it does |
|---------|-------------|
| `make check` | Run lint + all tests (use before committing) |
| `make test` | Run all tests (`uv run pytest -q`) |

## Git Workflow

- Use conventional commits: `<type>: <description>`.
- Do not switch branches, rebase, or merge into develop -- the orchestrator
  handles integration.
- Never push to remote. The orchestrator handles remote integration.
- Never add `Co-Authored-By` lines. No AI attribution in commits.

## Scope Discipline

- Focus on one coherent change per session.
- Do not include unrelated "while here" fixes.
- Fix broken behavior before adding new behavior.

## Documentation

- **ADRs** live in `docs/adr/NN-imperative-verb-phrase.md`.
- **Errata** live in `docs/errata/NN_snake_case_topic.md` -- for spec
  divergences.
- When you add or change user-facing behavior, public APIs, configuration, or
  architecture, update the relevant documentation in the same session.
