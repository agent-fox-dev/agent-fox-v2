# CLI Reference

Complete reference for all `agent-fox` commands, options, and configuration.

## Quick Reference

| Command | Description |
|---------|-------------|
| `agent-fox init` | Initialize project (creates `.agent-fox/`, develop branch, `.gitignore`, `AGENTS.md`) |
| `agent-fox plan` | Build execution plan from `.agent-fox/specs/` |
| `agent-fox code` | Execute the task plan via orchestrator |
| `agent-fox standup` | Generate daily activity report |
| `agent-fox fix` | Detect and auto-fix quality check failures |
| `agent-fox night-shift` | Run autonomous maintenance daemon (hunt scans + issue fixes) |
| `agent-fox reset` | Reset failed/blocked tasks for retry |
| `agent-fox lint-specs` | Validate specification files |
| `agent-fox insights` | Query review findings from the knowledge database |

## Global Options

```
agent-fox [OPTIONS] COMMAND [ARGS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--version` | | Show version and exit |
| `--verbose` | `-v` | Enable debug logging |
| `--quiet` | `-q` | Suppress info messages and banner |
| `--trace` | | Enable trace logging (includes bulk AI prompt/response payloads; implies `--verbose`) |
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
- **Logging to stderr:** All log messages go to stderr only -- stdout contains
  only valid JSON. Warning-level logs are also suppressed unless `--verbose`
  or `--trace` is active.
- **Stdin input:** When stdin is piped (not a TTY), the CLI reads a JSON
  object from stdin and uses its fields as parameter defaults. CLI flags
  take precedence over stdin fields. Unknown fields are silently ignored.

**Examples:**

```bash
# Get structured output from standup
agent-fox --json standup

# Combine with --verbose for JSON output + debug logs on stderr
agent-fox --json --verbose code
```

**Error handling:**

```bash
# Invalid JSON on stdin produces an error envelope
echo 'not json' | agent-fox --json code
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
| `--profiles` | flag | off | Copy default archetype profiles into `.agent-fox/profiles/` |

Creates the `.agent-fox/` directory structure with a default configuration file,
sets up the `develop` branch, updates `.gitignore`, creates
`.claude/settings.local.json` with canonical permissions, scaffolds an
`AGENTS.md` template with project instructions for coding agents, and creates
`.agent-fox/steering.md` as a placeholder for project-level agent directives. If
`AGENTS.md` already exists it is silently skipped to preserve customizations.
If `.agent-fox/steering.md` already exists it is also silently skipped.

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

**Steering document:** `init` creates `.agent-fox/steering.md` as an empty
placeholder on first run. This file is the user's persistent directive surface
-- add project-specific "always do X" or "never do Y" instructions here. All
agent sessions and bundled skills read this file and follow any directives it
contains. If the file contains only the initial placeholder text (no real
directives), it is silently skipped during prompt assembly so agents are not
distracted by empty templates.

**Profiles installation (`--profiles`):** When `--profiles` is provided, copies
all built-in archetype profiles (coder, reviewer, verifier, maintainer and
their mode variants) into `.agent-fox/profiles/`. Existing profile files are
preserved -- only missing profiles are created. This enables project-level
customization of agent behavior. See [Profiles](profiles.md) for details.

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
| `--specs-dir PATH` | path | from config | Path to specs directory (default: from config, or `.agent-fox/specs`) |

Scans `.agent-fox/specs/` for specification folders, parses task groups, builds a
dependency graph, resolves topological ordering, and persists the plan to the
DuckDB knowledge store. The plan is always rebuilt from `.agent-fox/specs/` on every
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
| `--debug` | flag | off | Enable debug audit trail (JSONL + DuckDB tool signals) |
| `--specs-dir PATH` | path | from config | Path to specs directory (default: from config, or `.agent-fox/specs`) |
| `--watch` | flag | off | Keep running and poll for new specs after all tasks complete |
| `--watch-interval N` | int | 60 | Seconds between watch polls (minimum: 10) |
| `--force-clean` | flag | off | Automatically remove untracked files and reset dirty index before dispatch |

Runs the orchestrator, which dispatches coding sessions to a Claude agent for
each ready task in the plan. Sessions execute in isolated git worktrees with
feature branches. After each session, results are harvested (merged) and state
is persisted to the DuckDB knowledge store.

Requires a persisted plan in the knowledge store (run `agent-fox plan` first).

The `--force-clean` flag overrides the `workspace.force_clean` config setting.
When active, the orchestrator automatically removes untracked files and resets
a dirty index before dispatching a session, instead of blocking the node.

#### Watch Mode (`--watch`)

When `--watch` is set, the orchestrator does not exit after all tasks complete.
Instead it enters a sleep-poll loop, re-running the sync barrier every
`--watch-interval` seconds to discover new specs added to `.agent-fox/specs/`. When new
ready tasks are found, normal dispatch resumes. This turns a single `code`
invocation into a long-lived process that picks up new work as it appears.

**Requirements for watch mode:**

- `hot_load` must be enabled in project configuration (default: on). If
  `hot_load` is disabled, `--watch` is silently ignored and the run terminates
  with COMPLETED status.
- `--watch-interval` must be >= 10 seconds (values below 10 are clamped to 10).

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

**Exit codes:** `0` success.

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

With `--auto`, after all checks pass, enters an improvement phase that uses an
analyzer-coder-verifier pipeline to iteratively improve the codebase. The
verifier validates each improvement; failures are rolled back. The phase ends
when the analyzer converges (no further improvements) or `--improve-passes`
is exhausted.

Detects checks by inspecting `pyproject.toml`, `package.json`, `Makefile`, and
`Cargo.toml`.

**Exit codes:** `0` all checks fixed (or improved), `1` checks remain,
none detected, or verifier failure.

---

### reset

Reset failed or blocked tasks for retry.

```
agent-fox reset [OPTIONS] [TASK_ID]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--hard` | | Full state wipe including completed tasks and code rollback |
| `--spec NAME` | | Reset all tasks for a single spec |
| `--yes` | `-y` | Skip confirmation prompt |

| Argument | Required | Description |
|----------|----------|-------------|
| `TASK_ID` | no | Reset only this specific task |

Without `TASK_ID`, resets all failed, blocked, and in-progress tasks (with
confirmation). Cleans up worktree directories and feature branches.

With `TASK_ID`, resets a single task and unblocks downstream dependents. No
confirmation prompt.

With `--spec`, resets all tasks belonging to a single spec. Mutually exclusive
with `--hard` and `TASK_ID`.

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
| `--no-specs` | flag | off | Disable the spec-executor stream |
| `--no-fixes` | flag | off | Disable the fix-pipeline stream |
| `--no-hunts` | flag | off | Disable the hunt-scan stream |
| `--specs-dir PATH` | path | from config | Path to specs directory (default: from config, or `.agent-fox/specs`) |

Night Shift is a continuously-running maintenance daemon that:

1. **Executes specs** -- discovers new specs in the specs directory and runs
   them through the full orchestrator pipeline.
2. **Hunts for maintenance issues** -- runs all enabled hunt categories (linter
   debt, dead code, test coverage gaps, dependency freshness, TODO/FIXME
   resolution, deprecated API usage, documentation drift, and quality gate
   checks) at the configured `hunt_scan_interval`. Each category uses static
   tooling followed by AI analysis to produce structured findings.
3. **Reports findings as platform issues** -- groups findings by root cause and
   creates one GitHub issue per group, including category, severity, affected
   files, and a suggested fix.
4. **Fixes `af:fix`-labelled issues** -- polls GitHub for open issues with the
   `af:fix` label at the configured `issue_check_interval`, then runs each
   through a coder + reviewer (fix-review mode) pipeline and opens a pull
   request.

**Requirements:**

- A `[platform]` configuration section with `type = "github"` and a valid
  `GITHUB_PAT` environment variable (or equivalent token). Night Shift aborts
  with exit code 1 if the platform is not configured.

**`--auto` flag:**

When `--auto` is active, every issue created during a hunt scan is
automatically labelled `af:fix`, making it eligible for autonomous fixing in
the same run. This enables a fully hands-off maintenance loop.

**Stream disable flags:**

Use `--no-specs`, `--no-fixes`, or `--no-hunts` to selectively disable
individual work streams. For example, `--no-hunts` runs only the spec executor
and fix pipeline without periodic hunt scans.

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

Send SIGINT (Ctrl-C) or SIGTERM once to request a graceful shutdown. The daemon
completes the currently active operation before exiting with code 0. Send a
second signal to abort immediately; exit code is 130.

**PID file:** The daemon writes a PID file to `.agent-fox/daemon.pid`. The
`code` and `plan` commands refuse to run while the daemon is active.

**Exit codes:**

| Code | Meaning |
|------|---------|
| `0` | Clean shutdown (SIGINT/SIGTERM or cost limit reached) |
| `1` | Startup failure (platform not configured, missing token) |
| `130` | Immediate abort (second interrupt signal) |

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

Runs structural validation rules against specs in `.agent-fox/specs/`: missing files,
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

When `--fix` produces changes, they are committed on a timestamped feature
branch (`lint-spec/fix-YYYYMMDD-HHMMSS`). The original branch is restored
after the commit.

**Exit codes:** `0` no errors (warnings OK), `1` error-severity findings.

---

### insights

Query review findings from the knowledge database.

```
agent-fox insights [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--spec NAME` | string | all | Filter by spec name |
| `--severity LEVEL` | string | all | Minimum severity level (`critical`, `major`, `minor`, `observation`) |
| `--archetype NAME` | string | all | Filter by archetype (`skeptic`, `verifier`, `oracle`) |
| `--run ID` | string | all | Filter by run ID |
| `--json` | flag | off | Output as JSON array |

Displays active (non-superseded) review findings from the knowledge store.
Findings are produced by Reviewer (pre-review, drift-review, audit-review
modes) and Verifier archetypes during `agent-fox code` sessions.

**Exit codes:** `0` success.

---

## Configuration

For the complete configuration reference, see [config-reference.md](config-reference.md).
