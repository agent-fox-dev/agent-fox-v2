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
# Initialize your project
agent-fox init

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

By default every task runs as a **Coder** agent. You can enable specialized
archetypes to add automated review and verification to the task graph:

| Archetype | Purpose | Injection |
|-----------|---------|-----------|
| **Coder** | Implements code (always enabled) | default |
| **Skeptic** | Reviews specs before coding begins | auto, before first coder group |
| **Verifier** | Checks code quality after coding | auto, after last coder group |
| **Librarian** | Documentation tasks | manual assignment |
| **Cartographer** | Architecture mapping | manual assignment |

Enable archetypes in your `config.toml`:

```toml
[archetypes]
skeptic = true
verifier = true

[archetypes.instances]
skeptic = 3       # run 3 independent reviewers, converge results

[archetypes.skeptic_settings]
block_threshold = 3  # block if > 3 majority-agreed critical findings
```

You can also assign archetypes to specific task groups in `tasks.md`:

```markdown
- [ ] 5. Update documentation [archetype: librarian]
```

See the [ADR](docs/adr/agent-archetypes.md) for design rationale.

### Adaptive Model Routing

agent-fox automatically selects the cheapest model tier that can handle each
task group. Simple tasks run on smaller, cheaper models; complex tasks run on
more capable ones. If a task fails, the system retries and then escalates to the
next tier automatically.

The routing system learns from past executions: after enough history
accumulates, a statistical model replaces the default heuristic rules and
predictions improve over time.

Configure routing behavior in `config.toml`:

```toml
[routing]
retries_before_escalation = 1   # retries at same tier before escalating (0-3)
training_threshold = 20         # min outcomes before training statistical model
accuracy_threshold = 0.75       # min accuracy to prefer statistical over LLM
retrain_interval = 10           # new outcomes between retraining cycles
```

Archetype model overrides act as tier ceilings — the system may start lower but
never escalates above the configured tier:

```toml
[archetypes.models]
coder = "STANDARD"    # coder tasks will never use ADVANCED
```

See the [ADR](docs/adr/adaptive-model-routing.md) for design rationale.

## Fox Tools (Token-Efficient File Tools)

agent-fox includes four token-efficient file tools that reduce token usage
and prevent silent corruption during file operations.

### Enabling Fox Tools

Add the following to your `config.toml`:

```toml
[tools]
fox_tools = true
```

When enabled, the session runner registers four tools with the agent backend:

| Tool | Description |
|------|-------------|
| `fox_outline` | Structural file outline (functions, classes, imports) with line ranges |
| `fox_read` | Read specific line ranges with per-line content hashes |
| `fox_edit` | Hash-verified atomic batch editing (prevents stale-read corruption) |
| `fox_search` | Regex search with context lines and content hashes |

### MCP Server

The fox tools are also available as an MCP server for external consumers
(other agents, IDEs, MCP-compatible clients):

```bash
# Launch the MCP server on stdio
agent-fox serve-tools

# Restrict file operations to specific directories
agent-fox serve-tools --allowed-dirs /path/to/project --allowed-dirs /path/to/other
```

The MCP server exposes the same four tools over the standard MCP stdio
transport. Path sandboxing via `--allowed-dirs` restricts file operations to
the specified directories and their descendants.

## Development

```bash
uv sync --group dev
make test              # all tests
make lint              # check lint + formatting
make check             # lint + all tests
```
