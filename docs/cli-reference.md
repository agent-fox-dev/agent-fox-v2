# CLI Reference

Complete reference for all `agent-fox` commands, options, and configuration.

## Quick Reference

| Command | Description |
|---------|-------------|
| `agent-fox init` | Initialize project (creates `.agent-fox/`, develop branch, `.gitignore`) |
| `agent-fox plan` | Build execution plan from `.specs/` |
| `agent-fox code` | Execute the task plan via orchestrator |
| `agent-fox status` | Show execution progress dashboard |
| `agent-fox standup` | Generate daily activity report |
| `agent-fox fix` | Detect and auto-fix quality check failures |
| `agent-fox reset` | Reset failed/blocked tasks for retry |
| `agent-fox ask` | Query project knowledge store |
| `agent-fox ingest` | Ingest ADRs and git commits into knowledge store |
| `agent-fox lint-spec` | Validate specification files |
| `agent-fox patterns` | Detect recurring cause-effect patterns |
| `agent-fox compact` | Deduplicate and compact the knowledge base |

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

# Ask a question with JSON input via stdin
echo '{"question": "What patterns exist?"}' | agent-fox --json ask

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
agent-fox init
```

Creates the `.agent-fox/` directory structure with a default configuration file,
sets up the `develop` branch, updates `.gitignore`, and creates
`.claude/settings.local.json` with canonical permissions.

Idempotent -- re-running on an already-initialized project preserves the
existing `config.toml`.

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
| `--verify` | flag | off | Verify dependency consistency (placeholder) |

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
agent-fox status
```

Displays task counts (done, in-progress, pending, failed, blocked), token
usage, estimated cost, and problem tasks with reasons.

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
| `--yes` | `-y` | Skip confirmation prompt |

| Argument | Required | Description |
|----------|----------|-------------|
| `TASK_ID` | no | Reset only this specific task |

Without `TASK_ID`, resets all failed, blocked, and in-progress tasks (with
confirmation). Cleans up worktree directories and feature branches.

With `TASK_ID`, resets a single task and unblocks downstream dependents. No
confirmation prompt.

**Exit codes:** `0` success, `1` error.

---

### ask

Ask a question about project knowledge.

```
agent-fox ask [OPTIONS] QUESTION
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--top-k N` | int | from config | Number of facts to retrieve |
| `--timeline` | flag | off | Return a causal timeline instead |

Embeds the question, retrieves relevant facts from the DuckDB knowledge store
via vector similarity search, and synthesizes a grounded answer with source
citations and confidence level.

With `--timeline`, returns a causal cause-effect chain instead of a synthesized
answer.

**Exit codes:** `0` success, `1` knowledge store unavailable.

---

### ingest

Ingest external knowledge sources.

```
agent-fox ingest [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--adrs / --no-adrs` | flag | on | Ingest ADRs from `docs/adr/` |
| `--git-commits / --no-git-commits` | flag | on | Ingest git commit messages |
| `--limit N` | int | 100 | Max git commits to ingest |
| `--since DATE` | string | none | Only commits after this date (ISO 8601) |

Parses ADR markdown files and git commit history, stores them as facts with
embeddings in the knowledge store for semantic search via `agent-fox ask`.

**Exit codes:** `0` success, `1` knowledge store unavailable.

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

### patterns

Detect recurring cause-effect patterns.

```
agent-fox patterns [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--min-occurrences N` | int | 2 | Minimum co-occurrences to report |

Analyzes session history and the causal graph to find recurring sequences
(e.g., "module X changes -> test Y breaks").

**Exit codes:** `0` always.

---

### compact

Compact the knowledge base.

```
agent-fox compact
```

Deduplicates facts by content hash (keeping the earliest) and resolves
supersession chains, then rewrites the JSONL file with surviving facts.

**Exit codes:** `0` always.

---

## Configuration

Configuration lives in `.agent-fox/config.toml`. All fields are optional;
defaults are used for any absent field. Unknown keys are logged and ignored.

### `[orchestrator]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `parallel` | int | `1` | Max parallel sessions (1-8) |
| `sync_interval` | int | `5` | Sessions between sync barriers (0 = disabled) |
| `hot_load` | bool | `true` | Scan for new specs at sync barriers |
| `max_retries` | int | `2` | Retries per failed task (0 = no retry) |
| `session_timeout` | int | `30` | Session timeout in minutes (min 1) |
| `inter_session_delay` | int | `3` | Seconds between sessions (0 = no delay) |
| `max_cost` | float | none | Cost ceiling in USD |
| `max_sessions` | int | none | Session count limit |

### `[models]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `coding` | string | `"ADVANCED"` | Model tier or ID for coding sessions |
| `coordinator` | string | `"STANDARD"` | Model tier or ID for coordination |
| `memory_extraction` | string | `"SIMPLE"` | Model tier or ID for fact extraction |
| `embedding` | string | `"voyage-3"` | Embedding model name |

Model tiers: `SIMPLE`, `STANDARD`, `ADVANCED`. You can also specify a model ID
directly (e.g., `claude-sonnet-4-6`).

### `[hooks]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `pre_code` | list[string] | `[]` | Scripts to run before each session |
| `post_code` | list[string] | `[]` | Scripts to run after each session |
| `sync_barrier` | list[string] | `[]` | Scripts to run at sync barriers |
| `timeout` | int | `300` | Hook timeout in seconds (min 1) |
| `modes` | dict | `{}` | Per-script failure mode (`"abort"` or `"warn"`) |

Default failure mode is `abort` (non-zero exit stops execution). Set a
script's mode to `"warn"` to log a warning and continue.

Hook environment variables: `AF_SPEC_NAME`, `AF_TASK_GROUP`, `AF_WORKSPACE`,
`AF_BRANCH`.

### `[security]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `bash_allowlist` | list[string] | none | Replace default command allowlist entirely |
| `bash_allowlist_extend` | list[string] | `[]` | Add commands to the default allowlist |

If both are set, `bash_allowlist` takes precedence (with a warning).

### `[theme]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `playful` | bool | `true` | Use fox-themed messages |
| `header` | string | `"bold #ff8c00"` | Rich style for headers |
| `success` | string | `"bold green"` | Rich style for success |
| `error` | string | `"bold red"` | Rich style for errors |
| `warning` | string | `"bold yellow"` | Rich style for warnings |
| `info` | string | `"#daa520"` | Rich style for info |
| `tool` | string | `"bold #cd853f"` | Rich style for tool output |
| `muted` | string | `"dim"` | Rich style for muted text |

### `[platform]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `type` | string | `"none"` | Platform type: `"none"` or `"github"` |
| `pr_granularity` | string | `"session"` | PR creation granularity |
| `wait_for_ci` | bool | `false` | Wait for CI checks after PR creation |
| `wait_for_review` | bool | `false` | Wait for PR review approval |
| `auto_merge` | bool | `false` | Auto-merge approved PRs |
| `ci_timeout` | int | `600` | CI wait timeout in seconds |
| `labels` | list[string] | `[]` | Labels to apply to PRs |

### `[memory]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `model` | string | `"SIMPLE"` | Model tier for memory extraction |

### `[knowledge]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `store_path` | string | `".agent-fox/knowledge.duckdb"` | DuckDB database path |
| `embedding_model` | string | `"all-MiniLM-L6-v2"` | Embedding model name (sentence-transformers) |
| `embedding_dimensions` | int | `384` | Embedding vector dimensions |
| `ask_top_k` | int | `20` | Default top-k for `ask` queries (min 1) |
| `ask_synthesis_model` | string | `"STANDARD"` | Model for answer synthesis |
