# CLI Reference

Complete reference for all `agent-fox` commands, options, and configuration.

## Quick Reference

| Command | Description |
|---------|-------------|
| `agent-fox init` | Initialize project (creates `.agent-fox/`, develop branch, `.gitignore`, `AGENTS.md`) |
| `agent-fox plan` | Build execution plan from `.specs/` |
| `agent-fox code` | Execute the task plan via orchestrator |
| `agent-fox status` | Show execution progress dashboard |
| `agent-fox standup` | Generate daily activity report |
| `agent-fox fix` | Detect and auto-fix quality check failures |
| `agent-fox night-shift` | Run autonomous maintenance daemon (hunt scans + issue fixes) |
| `agent-fox reset` | Reset failed/blocked tasks for retry |
| `agent-fox lint-specs` | Validate specification files |
| `agent-fox findings` | Query review findings from the knowledge database |
| `agent-fox onboard` | Populate the knowledge store for an existing codebase |

## Global Options

```
agent-fox [OPTIONS] COMMAND [ARGS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--version` | | Show version and exit |
| `--verbose` | `-v` | Enable debug logging |
| `--quiet` | `-q` | Suppress info messages and banner |
| `--json` | | Switch to structured JSON I/O mode |
| `--help` | | Show help and exit |

When invoked without a subcommand, displays help text.

### JSON Mode (`--json`)

The `--json` flag switches every command to structured JSON input/output mode,
designed for agent-to-agent and script-driven workflows.

**Behavior when active:**

- **Banner suppressed:** No ASCII art or version line on stdout.
- **Structured output:** Batch commands emit a single JSON object; streaming
  commands (`code`, `fix`) emit JSONL (one JSON object per line).
- **Error envelopes:** Failures emit `{"error": "<message>"}` to stdout with
  the original non-zero exit code preserved.
- **Logging to stderr:** All log messages go to stderr only — stdout contains
  only valid JSON.
- **Stdin input:** When stdin is piped (not a TTY), the CLI reads a JSON
  object from stdin and uses its fields as parameter defaults. CLI flags
  take precedence over stdin fields. Unknown fields are silently ignored.

**Examples:**

```bash
# Get project status as JSON
agent-fox --json status

# Combine with --verbose for JSON output + debug logs on stderr
agent-fox --json --verbose status
```

**Error handling:**

```bash
# Invalid JSON on stdin produces an error envelope
echo 'not json' | agent-fox --json status
# stdout: {"error": "invalid JSON input: ..."}
# exit code: 1
```

---

## Commands

### init

Initialize the current project for agent-fox.

```
agent-fox init [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--skills` | flag | off | Install bundled Claude Code skills into `.claude/skills/` |

Creates the `.agent-fox/` directory structure with a default configuration file,
sets up the `develop` branch, updates `.gitignore`, creates
`.claude/settings.local.json` with canonical permissions, scaffolds an
`AGENTS.md` template with project instructions for coding agents, and creates
`.specs/steering.md` as a placeholder for project-level agent directives. If
`AGENTS.md` already exists it is silently skipped to preserve customizations.
If `.specs/steering.md` already exists it is also silently skipped.

**Fresh init:** Generates `config.toml` programmatically from the Pydantic
configuration models. Every available option appears as a commented-out entry
with its description, valid range (if constrained), and default value.

**Re-init (config merge):** When `config.toml` already exists, `init` merges
it with the current schema non-destructively:

- **Preserves** all active (uncommented) user values.
- **Adds** new schema fields as commented-out entries with descriptions and
  defaults.
- **Marks deprecated** any active fields not recognized by the current schema
  with a `# DEPRECATED` prefix.
- **Preserves** user comments and formatting.
- **No-op** if the config is already up to date (byte-for-byte identical).
- If the existing file contains invalid TOML, a warning is logged and the
  file is left untouched.

**Steering document:** `init` creates `.specs/steering.md` as an empty
placeholder on first run. This file is the user's persistent directive surface
— add project-specific "always do X" or "never do Y" instructions here. All
agent sessions and bundled skills read this file and follow any directives it
contains. If the file contains only the initial placeholder text (no real
directives), it is silently skipped during prompt assembly so agents are not
distracted by empty templates.

**Skills installation (`--skills`):** When `--skills` is provided, copies
bundled skill templates from the agent-fox package into
`.claude/skills/{name}/SKILL.md`. Each skill becomes available as a slash
command in Claude Code (e.g., `/af-spec`, `/af-fix`). Existing skill files are
overwritten with the latest bundled versions. Works on both fresh init and
re-init. The output reports the number of skills installed. In JSON mode, the
output includes a `skills_installed` integer field.

**Exit codes:** `0` success, `1` not inside a git repository.

---

### plan

Build an execution plan from specifications.

```
agent-fox plan [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--fast` | flag | off | Exclude optional tasks |
| `--spec NAME` | string | all | Plan a single spec |
| `--analyze` | flag | off | Show parallelism analysis |

Scans `.specs/` for specification folders, parses task groups, builds a
dependency graph, resolves topological ordering, and persists the plan to
`.agent-fox/plan.json`. The plan is always rebuilt from `.specs/` on every
invocation.

**Exit codes:** `0` success, `1` plan error.

---

### code

Execute the task plan.

```
agent-fox code [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--parallel N` | int | from config | Override parallelism (1-8) |
| `--max-cost USD` | float | from config | Cost ceiling in USD |
| `--max-sessions N` | int | from config | Session count limit |
| `--debug` | flag | off | Enable debug audit trail (JSONL + DuckDB tool signals) |
| `--watch` | flag | off | Keep running and poll for new specs after all tasks complete |
| `--watch-interval N` | int | 60 | Seconds between watch polls (minimum: 10) |

Runs the orchestrator, which dispatches coding sessions to a Claude agent for
each ready task in the plan. Sessions execute in isolated git worktrees with
feature branches. After each session, results are harvested (merged) and state
is persisted to the DuckDB knowledge store.

Requires `.agent-fox/plan.json` to exist (run `agent-fox plan` first).

#### Watch Mode (`--watch`)

When `--watch` is set, the orchestrator does not exit after all tasks complete.
Instead it enters a sleep-poll loop, re-running the sync barrier every
`--watch-interval` seconds to discover new specs added to `.specs/`. When new
ready tasks are found, normal dispatch resumes. This turns a single `code`
invocation into a long-lived process that picks up new work as it appears.

**Requirements for watch mode:**

- `hot_load` must be enabled in project configuration (default: on). If
  `hot_load` is disabled, `--watch` is silently ignored and the run terminates
  with COMPLETED status.
- `--watch-interval` must be ≥ 10 seconds (values below 10 are clamped to 10).

**Example:**

```bash
# Keep the orchestrator running, check for new specs every 30 seconds
agent-fox code --watch --watch-interval 30
```

**Exit codes:**

| Code | Meaning |
|------|---------|
| `0` | All tasks completed |
| `1` | Error (plan missing, unexpected failure) |
| `2` | Stalled (no ready tasks, incomplete remain) |
| `3` | Cost or session limit reached |
| `130` | Interrupted (SIGINT) |

---

### status

Show execution progress dashboard.

```
agent-fox status [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--model` | flag | off | Include project model and critical path analysis |

Displays task counts (done, in-progress, pending, failed, blocked), token
usage, estimated cost, problem tasks with reasons, per-archetype cost breakdown,
and per-spec cost breakdown.

Use `agent-fox --json status` for structured JSON output.

**Exit codes:** `0` success, `1` plan missing.

---

### standup

Generate a daily activity report.

```
agent-fox standup [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--hours N` | int | 24 | Reporting window in hours |
| `--output PATH` | path | stdout | Write report to file |

Covers agent activity (sessions, tokens, cost), human commits, file overlaps
between agent and human work, and queue status (ready/pending/blocked tasks).

Use `agent-fox --json standup` for structured JSON output.

**Exit codes:** `0` success, `1` plan missing.

---

### fix

Detect and auto-fix quality check failures.

```
agent-fox fix [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--max-passes N` | int | 3 | Maximum fix iterations (min 1) |
| `--dry-run` | flag | off | Generate fix specs only, skip sessions |
| `--auto` | flag | off | After repair, run iterative improvement passes |
| `--improve-passes N` | int | 3 | Maximum improvement passes (requires `--auto`) |

Runs quality checks (pytest, ruff, mypy, npm test, cargo test, etc.), clusters
failures by root cause using AI, generates fix specifications, and runs coding
sessions to resolve them. Iterates until all checks pass or max passes reached.

Detects checks by inspecting `pyproject.toml`, `package.json`, `Makefile`, and
`Cargo.toml`.

**Exit codes:** `0` all checks fixed, `1` checks remain or none detected.

---

### reset

Reset failed or blocked tasks for retry.

```
agent-fox reset [OPTIONS] [TASK_ID]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--hard` | | Full state wipe including completed tasks and code rollback |
| `--yes` | `-y` | Skip confirmation prompt |

| Argument | Required | Description |
|----------|----------|-------------|
| `TASK_ID` | no | Reset only this specific task |

Without `TASK_ID`, resets all failed, blocked, and in-progress tasks (with
confirmation). Cleans up worktree directories and feature branches.

With `TASK_ID`, resets a single task and unblocks downstream dependents. No
confirmation prompt.

#### Hard Reset (`--hard`)

With `--hard`, performs a comprehensive state wipe:

- Resets **all** tasks to pending (including completed tasks).
- Cleans up all worktree directories and local feature branches.
- Compacts the knowledge base (deduplication and supersession).
- Rolls back the `develop` branch to its pre-task state (if commit
  tracking data is available).
- Preserves session history, token counters, and cost totals.

With `--hard <TASK_ID>`, performs a partial rollback:

- Rolls back `develop` to the commit immediately before the target task.
- Resets the target task and any tasks whose code is no longer on develop
  (cascaded reset).
- Earlier tasks remain completed.

Hard reset requires confirmation unless `--yes` or `--json` is provided.

**Exit codes:** `0` success, `1` error.

---

### night-shift

Run the autonomous maintenance daemon.

```
agent-fox night-shift [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--auto` | flag | off | Auto-assign the `af:fix` label to every issue created during hunt scans |

Night Shift is a continuously-running maintenance daemon that:

1. **Hunts for maintenance issues** — runs all enabled hunt categories (linter
   debt, dead code, test coverage gaps, dependency freshness, TODO/FIXME
   resolution, deprecated API usage, and documentation drift) at the configured
   `hunt_scan_interval`. Each category uses static tooling followed by AI
   analysis to produce structured findings.
2. **Reports findings as platform issues** — groups findings by root cause and
   creates one GitHub issue per group, including category, severity, affected
   files, and a suggested fix.
3. **Fixes `af:fix`-labelled issues** — polls GitHub for open issues with the
   `af:fix` label at the configured `issue_check_interval`, then runs each
   through the full skeptic → coder → verifier archetype pipeline and opens a
   pull request.

**Requirements:**

- A `[platform]` configuration section with `type = "github"` and a valid
  `GITHUB_PAT` environment variable (or equivalent token). Night Shift aborts
  with exit code 1 if the platform is not configured.

**`--auto` flag:**

When `--auto` is active, every issue created during a hunt scan is
automatically labelled `af:fix`, making it eligible for autonomous fixing in
the same run. This enables a fully hands-off maintenance loop.

**Scheduling:**

Both intervals run immediately on startup and then repeat on their configured
period. If a hunt scan is already running when the next interval fires, the
overlapping scan is skipped (logged as informational). If the platform API is
temporarily unavailable during an issue check, the error is logged as a
warning and the next interval retries normally.

**Cost control:**

Night Shift honours `orchestrator.max_cost` and `orchestrator.max_sessions`.
When the accumulated cost reaches `max_cost`, the daemon stops dispatching new
fix sessions and exits with code 0.

**Graceful shutdown:**

Send SIGINT (Ctrl-C) once to request a graceful shutdown. The daemon completes
the currently active operation before exiting with code 0. Send SIGINT a
second time to abort immediately; exit code is 130.

**Exit codes:**

| Code | Meaning |
|------|---------|
| `0` | Clean shutdown (SIGINT or cost limit reached) |
| `1` | Startup failure (platform not configured, missing token) |
| `130` | Immediate abort (second SIGINT) |

**Configuration:** See `[night_shift]` in [config-reference.md](config-reference.md).

---

### lint-specs

Validate specification files.

```
agent-fox lint-specs [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--ai` | flag | off | Enable AI-powered semantic analysis |
| `--fix` | flag | off | Auto-fix findings where possible |
| `--all` | flag | off | Lint all specs, including fully-implemented ones |

Use `agent-fox --json lint-specs` for structured JSON output.

Runs structural validation rules against specs in `.specs/`: missing files,
oversized task groups, missing verification subtasks, missing acceptance
criteria, broken cross-spec dependencies, and untraced requirements.

With `--ai`, additionally checks for vague or implementation-leaking acceptance
criteria.

With `--fix`, applies mechanical auto-fixes for supported rules (e.g., missing
verification subtasks, missing acceptance criteria).

With `--ai --fix`, additionally rewrites criteria flagged as `vague-criterion`
or `implementation-leak` using an AI-powered rewrite step. The system sends a
batched rewrite request per spec to the STANDARD-tier model, which returns
EARS-formatted replacement text. Rewrites preserve the original requirement ID
and are applied in-place to `requirements.md`. After rewrites, the spec is
re-validated to produce the final findings list. If the AI rewrite call fails,
the original criteria are left unchanged.

**Exit codes:** `0` no errors (warnings OK), `1` error-severity findings.

---

### findings

Query review findings from the knowledge database.

```
agent-fox findings [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--spec NAME` | string | all | Filter by spec name |
| `--severity LEVEL` | string | all | Minimum severity level (`critical`, `major`, `minor`, `observation`) |
| `--archetype NAME` | string | all | Filter by archetype (`skeptic`, `verifier`, `oracle`) |
| `--run ID` | string | all | Filter by run ID |
| `--json` | flag | off | Output as JSON array |

Displays active (non-superseded) review findings from the knowledge store.
Findings are produced by the Skeptic, Oracle, and Verifier archetypes during
`agent-fox code` sessions.

**Exit codes:** `0` success.

---

### onboard

Populate the knowledge store for an existing codebase.

```
agent-fox onboard [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--path DIR` | path | cwd | Project root directory |
| `--skip-entities` | flag | off | Skip entity graph analysis phase |
| `--skip-ingestion` | flag | off | Skip ADR/errata/git commit ingestion phase |
| `--skip-mining` | flag | off | Skip git pattern mining phase |
| `--skip-code-analysis` | flag | off | Skip LLM code analysis phase |
| `--skip-doc-mining` | flag | off | Skip LLM documentation mining phase |
| `--skip-embeddings` | flag | off | Skip embedding generation phase |
| `--model TIER` | string | `STANDARD` | Model tier for LLM phases |
| `--mining-days N` | int | 365 | Days of git history to analyze |
| `--fragile-threshold N` | int | 20 | Min commits to flag a file as a fragile area |
| `--cochange-threshold N` | int | 5 | Min co-occurrences for a co-change pattern |
| `--max-files N` | int | 0 (all) | Max source files for code analysis |

Runs a six-phase pipeline to bootstrap the knowledge store from an existing
codebase:

1. **Entity graph analysis** — builds a structural map of code entities and
   their relationships.
2. **Bootstrap ingestion** — ingests ADRs, errata, and significant git commits
   as knowledge facts.
3. **Git pattern mining** — analyzes commit history to identify fragile areas
   (frequently changed files) and co-change patterns (files that change
   together).
4. **LLM code analysis** — uses an LLM to extract patterns, conventions, and
   architectural decisions from source files.
5. **LLM documentation mining** — uses an LLM to extract knowledge from
   project documentation.
6. **Embedding generation** — generates vector embeddings for all facts to
   enable similarity search.

Use `--skip-*` flags to skip individual phases (useful for re-running after a
partial failure or to avoid LLM costs during testing).

**Exit codes:** `0` success.

---

## Configuration

For the complete configuration reference, see [config-reference.md](config-reference.md).
