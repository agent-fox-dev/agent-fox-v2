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
| `agent-fox reset` | Reset failed/blocked tasks for retry |
| `agent-fox dump` | Export knowledge store data (memory summary or full DB dump) |
| `agent-fox lint-spec` | Validate specification files |

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

### dump

Export knowledge store data as Markdown or JSON.

```
agent-fox dump [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--memory` | flag | off | Export memory summary to `docs/memory.md` (or `.json` with `--json`) |
| `--db` | flag | off | Export full database dump to `.agent-fox/knowledge_dump.md` (or `.json` with `--json`) |

Exactly one of `--memory` or `--db` must be provided. The two flags are
mutually exclusive.

**`--memory` mode:** Reads all active facts from the knowledge store and
writes them to `docs/memory.md` grouped by category. With the global `--json`
flag, writes `docs/memory.json` instead, containing a `facts` array and a
`generated` ISO-8601 timestamp.

**`--db` mode:** Discovers all tables in the knowledge store and writes each
table's contents to `.agent-fox/knowledge_dump.md` as Markdown tables. Cell
values longer than 120 characters are truncated. With `--json`, writes
`.agent-fox/knowledge_dump.json` with a `tables` dict keyed by table name.

The command opens the knowledge store in read-only mode, so it is safe to run
while an orchestrator session is active.

**Exit codes:** `0` success, `1` error (missing DB, no flags, both flags, no
tables).

---

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
`.claude/settings.local.json` with canonical permissions, and scaffolds an
`AGENTS.md` template with project instructions for coding agents. If
`AGENTS.md` already exists it is silently skipped to preserve customizations.

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
| `--reanalyze` | flag | off | Discard cached plan and rebuild |
| `--analyze` | flag | off | Show parallelism analysis |

Scans `.specs/` for specification folders, parses task groups, builds a
dependency graph, resolves topological ordering, and persists the plan to
`.agent-fox/plan.json`.

If a cached plan exists and `--reanalyze` is not set, the cached plan is
loaded and displayed without rebuilding.

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
| `--no-hooks` | flag | off | Skip all hook scripts |
| `--max-cost USD` | float | from config | Cost ceiling in USD |
| `--max-sessions N` | int | from config | Session count limit |
| `--debug` | flag | off | Enable debug audit trail (JSONL + DuckDB tool signals) |

Runs the orchestrator, which dispatches coding sessions to a Claude agent for
each ready task in the plan. Sessions execute in isolated git worktrees with
feature branches. After each session, results are harvested (merged) and state
is persisted to `.agent-fox/state.jsonl`.

Requires `.agent-fox/plan.json` to exist (run `agent-fox plan` first).

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

### lint-spec

Validate specification files.

```
agent-fox lint-spec [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--ai` | flag | off | Enable AI-powered semantic analysis |
| `--fix` | flag | off | Auto-fix findings where possible |
| `--all` | flag | off | Lint all specs, including fully-implemented ones |

Use `agent-fox --json lint-spec` for structured JSON output.

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

## Configuration

For the complete configuration reference, see [configuration.md](configuration.md).
