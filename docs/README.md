# agent-fox Documentation

## How It Works

You write a spec, run `agent-fox code`, and walk away. The fox reads your
specs, plans the work, spins up isolated git worktrees, runs each coding
session with the right context, handles merge conflicts, retries failures,
extracts learnings into structured memory, and merges clean commits to
`develop`. You come back to a finished feature branch and a standup report.

The typical workflow has four stages:

1. **Write specs.** Describe your feature as a structured specification
   package — a PRD, acceptance criteria, design document, test contracts, and
   a task list — under `.specs/`. Use the `/af-spec` skill in Claude Code to
   generate these from a PRD, a GitHub issue URL, or a plain-English
   description.

2. **Plan.** Run `agent-fox plan` to compile your specs into a dependency
   graph of tasks. The planner is deterministic — same specs, same graph,
   every time. Inspect the plan, adjust dependencies, and re-plan if needed.

3. **Execute.** Run `agent-fox code --parallel 4` to start autonomous
   execution. The orchestrator dispatches agents to each ready task in
   dependency order. Each agent works in an isolated git worktree. Review
   agents check specs before coding starts; verification agents check the
   result after. Failed tasks are retried with escalation to stronger models.
   Completed work is merged into `develop` under a serializing lock.

4. **Monitor.** Run `agent-fox status` for a progress dashboard (task counts,
   cost, blocked tasks) or `agent-fox standup` for a daily activity report.

For ongoing codebase health, `agent-fox night-shift` runs as a maintenance
daemon — it hunts for technical debt, files GitHub issues, and autonomously
fixes the ones you approve.

## Architecture

For a detailed understanding of how agent-fox works internally — spec
structure, graph construction, session lifecycle, agent archetypes, the
knowledge system, and the night-shift daemon — see the
[Architecture Guide](architecture/README.md).

## Reference

| Document | Description |
|----------|-------------|
| [CLI Reference](cli-reference.md) | All commands, flags, and exit codes |
| [Configuration Reference](config-reference.md) | Every `config.toml` section and option |
| [Archetypes](archetypes.md) | Agent archetype details and configuration |
| [Skills](skills.md) | Claude Code skill reference |
| [Architecture Guide](architecture/README.md) | System internals and design rationale |
