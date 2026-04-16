# agent-fox Documentation

## How It Works

You write a spec, run `agent-fox code`, and walk away. The fox reads your
specs, plans the work, spins up isolated git worktrees, runs each coding
session with the right context, handles merge conflicts, retries failures,
extracts learnings into structured memory, and merges clean commits to
`develop`. You come back to a finished feature branch and a standup report.

### The Workflow

The typical workflow has four stages:

1. **Write specs.** Describe your feature as a structured specification
   package under `.specs/` — a PRD, acceptance criteria (EARS syntax), design
   document, test contracts, and a task list. Each spec maps to one coherent
   feature or change. Use the `/af-spec` skill in Claude Code to generate the
   full five-file package from a PRD, a GitHub issue URL, or a plain-English
   description. Run `agent-fox lint-specs` to validate specs before planning;
   use `--fix` to auto-repair common issues and `--ai` for semantic analysis
   of acceptance criteria.

2. **Plan.** Run `agent-fox plan` to compile your specs into a dependency
   graph of tasks. The planner is deterministic — same specs, same graph,
   every time. It parses task groups from each spec, builds intra-spec chains
   (groups execute sequentially), wires cross-spec dependencies declared in
   PRDs, and injects review agents at the right positions. Use `--analyze` to
   see a parallelism analysis, or `--fast` to exclude optional tasks.

3. **Execute.** Run `agent-fox code --parallel 4` to start autonomous
   execution. The orchestrator dispatches agents to each ready task in
   dependency order. Each agent works in an isolated git worktree on its own
   feature branch, so multiple agents work simultaneously without conflicts.
   Review agents (Skeptic, Oracle) check specs before coding starts;
   verification agents (Auditor, Verifier) check the result after. Failed
   tasks are retried with escalation to stronger models. Completed work is
   merged into `develop` under a serializing lock via squash merge (with
   AI-assisted conflict resolution when needed).

4. **Monitor.** Run `agent-fox status` for a progress dashboard — task counts
   by state, token usage, estimated cost, cost breakdown by archetype and
   spec, and details on any blocked or failed tasks. Run `agent-fox standup`
   for a daily activity report covering agent sessions, human commits, and
   file overlaps. Both commands support `--json` for machine consumption.

### Agent Archetypes

agent-fox uses five specialized agent archetypes to divide labor:

- **Coder** — the primary implementation agent. Receives the full spec
  context and implements one task group per session. Follows a test-first
  workflow: group 1 writes failing tests, subsequent groups implement code.
- **Skeptic** — reviews spec quality before implementation. Checks
  completeness, consistency, feasibility, testability, edge cases, and
  security. Can block coding if critical findings exceed a threshold.
- **Oracle** — validates spec assumptions against the actual codebase.
  Detects drift between what specs expect and what actually exists.
  Automatically skipped when the spec references no existing code.
- **Auditor** — validates test quality against test spec contracts after
  tests are written. Triggers coder retries when tests are missing, weak,
  or misaligned with their specifications.
- **Verifier** — performs post-implementation verification. Runs the test
  suite, checks each requirement against acceptance criteria, and triggers
  coder retries when verification fails.

Review archetypes can run multiple instances in parallel on the same task,
with their outputs merged using archetype-specific convergence strategies.
For full archetype details, see [Archetypes](archetypes.md).

### Quality Fixes

When quality checks are failing, run `agent-fox fix` to auto-detect available
tools (pytest, ruff, mypy, etc.), cluster failures by root cause using AI,
generate fix specs, and dispatch coding agents to resolve each cluster. Use
`--auto` for iterative improvement passes after the initial repair.

### Night Shift

For ongoing codebase health, `agent-fox night-shift` runs as a continuously
running maintenance daemon. It hunts for technical debt across eight
categories — linter debt, dead code, test coverage gaps, dependency freshness,
deprecated API usage, documentation drift, TODO/FIXME resolution, and quality
gate failures — then groups findings by root cause and files GitHub issues.
Issues labelled `af:fix` are automatically picked up and repaired through a
three-agent pipeline (Skeptic, Coder, Verifier). Use `--auto` to label every
discovered issue for hands-off repair.

### Knowledge System

agent-fox maintains a persistent knowledge store (DuckDB) that captures what
agents learn during sessions — patterns, gotchas, architectural decisions,
conventions, anti-patterns, and fragile areas. Each new session starts with
a fresh context window but receives curated, relevant facts from prior
sessions so the same mistakes are never repeated. The knowledge system handles
deduplication, contradiction detection, and age-based confidence decay
automatically. Run `agent-fox onboard` to bootstrap the knowledge store from
an existing codebase by ingesting ADRs, git history, and source analysis.

### Recovery

When tasks fail or become blocked, run `agent-fox reset` to clear failed
tasks and retry them. For targeted recovery, pass a specific task ID. For a
full restart, use `--hard` to reset all tasks, clean up worktrees and
branches, compact the knowledge store, and roll back `develop`.

## Architecture

For a detailed understanding of how agent-fox works internally — how specs
become task graphs, how the orchestrator dispatches and serializes sessions,
the archetype mode system, the knowledge lifecycle, and the night-shift
hunt-triage-fix pipeline — see the [Architecture Guide](architecture/README.md).
The architecture docs are written for senior engineers joining the project and
stay at the conceptual level without code snippets or class hierarchies.

## Reference

| Document | Description |
|----------|-------------|
| [CLI Reference](cli-reference.md) | All commands, flags, and exit codes |
| [Configuration Reference](config-reference.md) | Every `config.toml` section and option |
| [Archetypes](archetypes.md) | Agent archetype details and configuration |
| [Skills](skills.md) | Claude Code skill reference |
| [Architecture Guide](architecture/README.md) | System internals and design rationale |
