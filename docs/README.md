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
   package under `.agent-fox/specs/` — a PRD, acceptance criteria (EARS syntax), design
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
   Reviewer agents (pre-review, drift-review modes) check specs before
   coding starts; audit-review and Verifier agents check the result after. Failed
   tasks are retried with escalation to stronger models. Completed work is
   merged into `develop` under a serializing lock via squash merge (with
   AI-assisted conflict resolution when needed).

4. **Monitor.** Run `agent-fox standup` for an activity report covering
   agent sessions, human commits, and file overlaps. Run
   `agent-fox insights` for a structured view of review findings, drift
   reports, and verification verdicts across specs. Both commands support
   `--json` for machine consumption.

### Agent Archetypes

agent-fox uses a four-entry archetype registry with a mode system to divide
labor:

- **Coder** — the primary implementation agent. Receives the full spec
  context and implements one task group per session. Follows a test-first
  workflow: group 1 writes failing tests, subsequent groups implement code.
- **Reviewer** — a single archetype with four modes that cover all review
  roles:
  - *pre-review* — reviews spec quality before implementation. Checks
    completeness, consistency, feasibility, and security. Can block coding
    if critical findings exceed a threshold.
  - *drift-review* — validates spec assumptions against the actual codebase.
    Detects drift between what specs expect and what actually exists.
    Automatically skipped when the spec references no existing code.
  - *audit-review* — validates test quality against test spec contracts
    after tests are written. Triggers coder retries when tests are missing,
    weak, or misaligned with their specifications.
  - *fix-review* — reviews fix-mode patches (quality fixes, night-shift
    repairs) with full tool access and extended turn budget.
- **Verifier** — performs post-implementation verification. Runs the test
  suite, checks each requirement against acceptance criteria, and triggers
  coder retries when verification fails.
- **Maintainer** — drives night-shift operations with three modes (hunt,
  fix-triage, extraction). Not assignable to spec tasks.

Review and verification archetypes can run multiple instances in parallel on
the same task, with outputs merged using mode-specific convergence strategies.
For full archetype details, see the
[Archetypes section](architecture/03-execution-and-archetypes.md#agent-archetypes)
in the Architecture Guide.

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
two-agent pipeline (Coder, Reviewer in fix-review mode). Use `--auto` to label every
discovered issue for hands-off repair.

### Knowledge System

agent-fox maintains a persistent knowledge store (DuckDB) that provides
institutional memory across sessions. Each new session starts with a fresh
context window but receives curated, relevant knowledge from prior sessions
so agents build on each other's work rather than starting blind.

The knowledge system tracks eight categories of context: review findings,
verification verdicts, errata, architecture decision records, cross-group
findings, same-spec session summaries, cross-spec session summaries, and
prior-run findings. Findings follow a closed-loop lifecycle — when a finding
is injected into a session and the session completes, the finding is
automatically superseded. This keeps the active knowledge set current without
manual intervention.

ADR files (`docs/adr/*.md`) created during coding sessions are automatically
detected and indexed, making architectural decisions discoverable by future
sessions working on related specs.

### Recovery

When tasks fail or become blocked, run `agent-fox reset` to clear failed
tasks and retry them. For targeted recovery, pass a specific task ID. For a
full restart, use `--hard` to reset all tasks, clean up worktrees and
branches, compact the knowledge store, and roll back `develop`.

## Architecture

For a detailed understanding of how agent-fox works internally, start with
the [Coding Session Architecture](architecture.md) — a top-down walkthrough
covering persistent state, the orchestrator's dispatch loop, session
lifecycle, prompt construction, the knowledge system, and worktree/git
architecture. For topic-specific deep dives, see the
[Architecture Guide](architecture/README.md). Both are written for senior
engineers joining the project and stay at the conceptual level without code
snippets or class hierarchies.

## Reference

| Document | Description |
|----------|-------------|
| [Coding Session Architecture](architecture.md) | Top-down walkthrough of session and knowledge system |
| [CLI Reference](cli-reference.md) | All commands, flags, and exit codes |
| [Configuration Reference](config-reference.md) | Every `config.toml` section and option |
| [Archetypes](architecture/03-execution-and-archetypes.md#agent-archetypes) | Archetype registry, modes, and convergence |
| [Profiles](profiles.md) | Agent profiles, resolution, and customization |
| [Skills](skills.md) | Claude Code skill reference |
| [Architecture Guide](architecture/README.md) | Topic-specific architecture deep dives |
