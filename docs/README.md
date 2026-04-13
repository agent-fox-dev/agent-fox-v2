# agent-fox Documentation

## How It Works

You write a spec, run `agent-fox code`, and walk away. The fox reads your
specs, plans the work, spins up isolated git worktrees, runs each coding
session with the right context, handles merge conflicts, retries failures,
extracts learnings into structured memory, and merges clean commits to
`develop`. You come back to a finished feature branch and a standup report.

### Spec-Driven Development

Your project needs specs under `.specs/` before running `plan` or `code`.
Use the [`/af-spec`](skills.md#af-spec) skill in Claude Code to generate
them from a PRD, a GitHub issue, or a plain-English description:

```
/af-spec [path-to-prd-or-prompt-or-github-issue-url]
```

Each spec folder contains five artifacts with full traceability:

| File | Content |
|------|---------|
| `prd.md` | Product requirements document (source of truth) |
| `requirements.md` | EARS-syntax acceptance criteria |
| `design.md` | Architecture, interfaces, correctness properties |
| `test_spec.md` | Language-agnostic test contracts |
| `tasks.md` | Implementation plan with checkboxes |

### Agent Archetypes

By default every task runs as a **Coder** agent. Specialized archetypes add
automated review and verification at different stages of the pipeline:

| Archetype | Purpose | Default |
|-----------|---------|---------|
| **Coder** | Implements code | always enabled |
| **Skeptic** | Reviews specs before coding | enabled |
| **Oracle** | Validates spec assumptions against codebase | disabled |
| **Auditor** | Validates test code against test_spec contracts | disabled |
| **Verifier** | Checks code quality after coding | enabled |
| **Librarian** | Documentation tasks | disabled |
| **Cartographer** | Architecture mapping | disabled |

See the [archetypes reference](archetypes.md) for details on each archetype.

### Adaptive Model Routing

agent-fox automatically selects the cheapest model tier that can handle each
task group. Simple tasks run on smaller, cheaper models; complex tasks run on
more capable ones. If a task fails, the system retries and then escalates to
the next tier automatically.

The routing system learns from past executions: after enough history
accumulates, a statistical model replaces the default heuristic rules and
predictions improve over time.

See the [configuration reference](configuration.md#routing) for routing
options.

## Dependencies

### DuckDB (Required)

DuckDB is a **hard requirement** for all agent-fox operations. The knowledge
store (an embedded DuckDB database) must be available for sessions to run.
If DuckDB cannot be initialized, agent-fox will abort immediately with a
clear error message rather than running with degraded functionality.

## Reference

| Document | Description |
|----------|-------------|
| [CLI Reference](cli-reference.md) | All commands, flags, and exit codes |
| [Configuration](config-reference.md) | Every `config.toml` section and option |
| [Archetypes](archetypes.md) | Agent archetype details and configuration |
| [Skills](skills.md) | Claude Code skill reference |
