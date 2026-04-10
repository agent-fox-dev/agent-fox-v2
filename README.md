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

Requires a GitHub platform configured in `.agent-fox/config.toml` (`[platform] type = "github"`).
See the [Night Shift CLI reference](docs/cli-reference.md#night-shift) and
[configuration](docs/configuration.md#night_shift) for full details.

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
- [Configuration Reference](docs/config-reference.md) — every `config.toml` option (all sections and fields)
- [Archetypes](docs/archetypes.md) — agent roles (Coder, Skeptic, Oracle, Auditor, Verifier, …)
- [Skills](docs/skills.md) — bundled Claude Code slash commands (`/af-spec`, `/af-fix`, …)

## Scope Guard — Stub Enforcement

The Scope Guard subsystem prevents wasted coder sessions by enforcing that
test-writing task groups produce only stubs (not full implementations) for
non-test code.

### Stub Enforcement

When a task group has a test-writing archetype, the system:

1. **Prompt Injection** — Injects a `SCOPE_GUARD:STUB_ONLY` directive into the
   coder session prompt, instructing the agent to produce only type signatures
   and stub bodies for all non-test code.

2. **Post-Session Validation** — After the session completes, scans all
   non-test source files modified by the session and verifies that every new or
   modified function body contains only stub placeholders.

3. **Violation Reporting** — If non-stub implementations are found in non-test
   code, the session is flagged with a stub-enforcement violation and a warning
   is emitted to the operator.

### Supported Languages

Stub detection supports the following languages and placeholder patterns:

| Language | Stub Placeholders |
|:---------|:------------------|
| **Rust** | `todo!()`, `unimplemented!()`, `panic!("not implemented")` |
| **Python** | `raise NotImplementedError`, `pass` (as sole body statement) |
| **TypeScript/JavaScript** | `throw new Error("not implemented")` |

A function body is classified as a stub only if its entire content (after
stripping comments and whitespace) consists of a single recognized placeholder.
Any additional statements alongside a placeholder disqualify it as a stub.

### Test Block Exclusion

Stub enforcement applies only to production code. Functions inside
language-appropriate test blocks are excluded:

- **Rust** — code inside `#[cfg(test)]` modules or `#[test]` functions
- **Python** — files matching `test_*.py` / `*_test.py`, or functions starting
  with `test_`, or classes inheriting from `unittest.TestCase`
- **TypeScript/JavaScript** — files matching `*.test.ts` / `*.spec.ts` /
  `*.test.js` / `*.spec.js`, or code inside `describe()` / `it()` / `test()`
  blocks

Files in unsupported languages are skipped with a warning logged.

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
