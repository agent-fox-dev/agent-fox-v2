# agent-fox

<p align="center">
    <picture>
        <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/agent-fox-dev/agent-fox/refs/heads/main/docs/assets/agent-fox-mascot.png">
        <img src="https://raw.githubusercontent.com/agent-fox-dev/agent-fox/refs/heads/main/docs/assets/agent-fox-mascot.png" width="200">
    </picture>
</p>

**Point agent-fox at a spec. Walk away. Come back to working code across 50+
commits.**

agent-fox is an autonomous coding-agent orchestrator built exclusively for
Claude. It reads your specifications, builds a dependency graph of tasks, and
drives Claude coding agents through each one — in parallel, in isolated
worktrees, with structured memory, adaptive model routing, and multi-archetype
review pipelines.

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

## Installation

```bash
uv tool install agent-fox
```

Or install directly from the repository:

```bash
uv tool install git+https://github.com/agent-fox-dev/agent-fox.git
```

## Quick Start

```bash
# Initialize your project (use --skills to install Claude Code skills)
agent-fox init --skills

# Create the task graph from your specs
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

## Documentation

Full documentation lives in [`docs/`](docs/README.md):

- [CLI Reference](docs/cli-reference.md) — all commands, flags, and exit codes
- [Configuration](docs/configuration.md) — every `config.toml` option
- [Archetypes](docs/archetypes.md) — agent roles (Coder, Skeptic, Oracle, Auditor, Verifier, …)
- [Skills](docs/skills.md) — bundled Claude Code slash commands (`/af-spec`, `/af-fix`, …)

## Development

```bash
uv sync --group dev
make test              # all tests
make lint              # check lint + formatting
make check             # lint + all tests
```

`uv sync` installs the project in editable mode, so changes you make to the
source are immediately reflected when you run `agent-fox`. To run the local
version explicitly (rather than a globally installed release):

```bash
uv run agent-fox <command>
```
