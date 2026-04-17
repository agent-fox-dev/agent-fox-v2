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

Your project needs specs under `.agent-fox/specs/` before running `plan` or `code`.

Use the `/af-spec` skill in Claude Code to generate them from a PRD,
a GitHub issue or a plain-English description:

```
/af-spec [path-to-prd-or-prompt-or-github-issue-url]
```

### Night Shift — Autonomous Maintenance

Keep your codebase healthy while you sleep. Night Shift is a continuously-running
maintenance daemon that hunts for linter debt, dead code, test coverage gaps,
outdated dependencies, and more — then files GitHub issues and autonomously fixes
the ones labelled `af:fix`.

```bash
# Start the maintenance daemon (Ctrl-C to stop gracefully)
agent-fox night-shift

# Automatically label every discovered issue as af:fix for hands-off repair
agent-fox night-shift --auto
```

## Installation

```bash
uv tool install agent-fox
```

Or install directly from the repository:

```bash
uv tool install git+https://github.com/agent-fox-dev/agent-fox.git
```

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

## Documentation

Full documentation lives in [`docs/`](docs/README.md):

- [CLI Reference](docs/cli-reference.md) — all commands, flags, and exit codes
- [Configuration Reference](docs/config-reference.md) — every `config.toml` option (all sections and fields)
- [Agent Archetypes](docs/architecture/03-execution-and-archetypes.md#agent-archetypes) — archetype registry, modes, convergence
- [Skills](docs/skills.md) — bundled Claude Code slash commands (`/af-spec`, `/af-fix`, …)

For a deeper understanding of the system's internals — how specs become task
graphs, how agents are dispatched in parallel, how the knowledge store works,
and how night-shift discovers and fixes technical debt — see the
[Architecture Guide](docs/architecture/README.md).

## References

agent-fox draws on ideas from the following research:

- **MAGMA** — A multi-graph memory architecture for AI agents. agent-fox's
  knowledge system uses a similar approach: typed facts with causal links,
  embedding-based retrieval, and lifecycle management (deduplication,
  contradiction detection, decay).
  [arXiv:2601.03236](https://arxiv.org/abs/2601.03236)

- **Sleep-time Compute** — Explores how pre-computation outside of inference
  time can improve agent performance. Night-shift's autonomous maintenance
  model applies this principle: the system does useful work while the
  developer is away, so the codebase is healthier when they return.
  [arXiv:2504.13171](https://arxiv.org/html/2504.13171v1)

- **Memory in the Age of AI Agents: A Survey** — A comprehensive survey of
  memory architectures for AI agents. Provides context for agent-fox's
  design choices around fact extraction, supersession, and retrieval.
  [GitHub](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)

---
Built exclusively for Claude.