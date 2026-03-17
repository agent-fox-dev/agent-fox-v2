# agent-fox

<p align="center">
    <picture>
        <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/agent-fox-dev/agent-fox-v2/refs/heads/main/docs/assets/agent-fox-mascot.png">
        <img src="https://raw.githubusercontent.com/agent-fox-dev/agent-fox-v2/refs/heads/main/docs/assets/agent-fox-mascot.png" width="200">
    </picture>
</p>

**Point agent-fox at a spec. Walk away. Come back to working code across 50+
commits.**

agent-fox is an autonomous coding-agent orchestrator. It reads your
specifications, builds a dependency graph of tasks, and drives 
Claude coding agents through each one.

## Before agent-fox

You write a spec, then sit in front of your terminal babysitting an AI agent
for hours. You paste context, fix merge conflicts, restart after crashes, and
lose track of what's done. 

By session 10 you're exhausted and the agent has forgotten everything from session 1.

## With agent-fox

You write the same spec, run `agent-fox code`, and go do something else.

The fox reads your specs, plans the work, spins up isolated worktrees, runs each
session with the right context, handles merge conflicts, retries failures,
extracts learnings into structured memory, and merges clean commits to
`develop`. 

You come back to a finished feature branch and a standup report.

## Quick start

```bash
# Initialize your project (use --skills to install Claude Code skills)
agent-fox init --skills

# Create the task graph
agent-fox plan 

# Run autonomous coding sessions with 4 agents in parallel
agent-fox code --parallel 4

# Check progress
agent-fox status
```

See the [CLI reference](docs/cli-reference.md) for all command options.

### Spec-driven Development

Your project needs specs under `.specs/` before running `plan` or `code`.

Use the `/af-spec` skill in Claude Code to generate them from a PRD,
a GitHub issue or a plain-English description:

```
/af-spec [path-to-prd-or-prompt-or-github-issue-url]
```

agent-fox ships with a set of [Claude Code skills](docs/skills.md) that assist
with spec authoring, architecture decisions, code simplification, and more.

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

Skeptic and Verifier are enabled by default. Configure archetypes in your
`config.toml`:

```toml
[archetypes]
oracle = true         # enable oracle (disabled by default)
```

See the [archetypes reference](docs/archetypes.md) for details on each
archetype, and the [ADR](docs/adr/agent-archetypes.md) for design rationale.

### Adaptive Model Routing

agent-fox automatically selects the cheapest model tier that can handle each
task group. Simple tasks run on smaller, cheaper models; complex tasks run on
more capable ones. If a task fails, the system retries and then escalates to the
next tier automatically.

The routing system learns from past executions: after enough history
accumulates, a statistical model replaces the default heuristic rules and
predictions improve over time.

See the [configuration reference](docs/configuration.md#routing) for routing
options and the [ADR](docs/adr/adaptive-model-routing.md) for design rationale.

## Fox Tools (Token-Efficient File Tools)

agent-fox includes four token-efficient file tools that reduce token usage
and prevent silent corruption during file operations.

Fox tools are enabled by default. When enabled, the session runner registers
four tools with the agent backend:

| Tool | Description |
|------|-------------|
| `fox_outline` | Structural file outline (functions, classes, imports) with line ranges |
| `fox_read` | Read specific line ranges with per-line content hashes |
| `fox_edit` | Hash-verified atomic batch editing (prevents stale-read corruption) |
| `fox_search` | Regex search with context lines and content hashes |

## Dependencies

### DuckDB (Required)

DuckDB is a **hard requirement** for all agent-fox operations. The knowledge
store (an embedded DuckDB database) must be available for sessions to run.
If DuckDB cannot be initialized, agent-fox will abort immediately with a
clear error message rather than running with degraded functionality.

All knowledge-dependent features (memory facts, causal links, review findings,
session outcomes, complexity assessments) require a working DuckDB connection.

## Documentation

| Document | Description |
|----------|-------------|
| [CLI Reference](docs/cli-reference.md) | All commands, flags, and options |
| [Configuration Reference](docs/configuration.md) | All `config.toml` sections and options |
| [Archetypes](docs/archetypes.md) | Agent archetype details and configuration |
| [Skills](docs/skills.md) | Claude Code skill reference |

## Development

```bash
uv sync --group dev
make test              # all tests
make lint              # check lint + formatting
make check             # lint + all tests
```
