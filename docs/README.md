# agent-fox Documentation

## How It Works

You write a spec, run `agent-fox code`, and walk away. The fox reads your
specs, plans the work, spins up isolated git worktrees, runs each coding
session with the right context, handles merge conflicts, retries failures,
extracts learnings into structured memory, and merges clean commits to
`develop`. You come back to a finished feature branch and a standup report.

TBD: give a ver high-level overview of how agent-fox works, from a user's perspctive.

TBD: Provide a link to the "real" architectire docs in docs/architecture and give a short intro to the architecture section. 2-3 sentences only.

TBD: create an index to the detailled docs, especially the CLI reference and Configuration.

## Reference

| Document | Description |
|----------|-------------|
| [CLI Reference](cli-reference.md) | All commands, flags, and exit codes |
| [Configuration](config-reference.md) | Every `config.toml` section and option |
| [Archetypes](archetypes.md) | Agent archetype details and configuration |
| [Skills](skills.md) | Claude Code skill reference |
